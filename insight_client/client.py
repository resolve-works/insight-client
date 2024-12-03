import time
import webbrowser
import requests
import os
import base64
import json
import keyring
import logging
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from pathlib import Path
from xml.etree import ElementTree
from oauthlib.oauth2 import DeviceClient
from oauthlib.oauth2.rfc6749.errors import CustomOAuth2Error
from requests_oauthlib import OAuth2Session
from enum import Enum
from urllib.parse import urlparse, urlencode
from typing import BinaryIO
from minio import Minio
from .config import get_option, config


logging.basicConfig(level=logging.INFO)


class InodeType(Enum):
    FOLDER = "folder"
    FILE = "file"


class InodeExistsException(Exception):
    pass


class InsightClient(OAuth2Session):
    def create_inode(
        self, name: str, inode_type: InodeType, parent_id: str | None = None
    ):
        # Create inode model
        response = self.post(
            os.path.join(get_option("api", "endpoint"), "inodes"),
            data={
                "name": name,
                "type": inode_type.value,
                "parent_id": parent_id,
            },
            headers={"Prefer": "return=representation"},
        )

        if response.status_code != 201:
            data = response.json()
            # Duplicate key value on unique constraint
            if data["code"] == "23505":
                raise InodeExistsException()
            else:
                raise Exception(data["message"])

        return response.json()[0]

    def get_inode(self, name: str, parent_id: str | None = None):
        url = os.path.join(get_option("api", "endpoint"), "inodes")
        params = {"name": f"eq.{name}"}
        if parent_id:
            params["parent_id"] = f"eq.{parent_id}"

        res = self.get(url + "?" + urlencode(params))
        return res.json()[0]

    def mark_file_uploaded(self, id: str):
        # Mark file as uploaded in backend
        res = self.patch(
            os.path.join(get_option("api", "endpoint"), "inodes") + f"?id=eq.{id}",
            data={"is_uploaded": True},
        )
        if res.status_code != 204:
            data = res.json()
            raise Exception(data["message"])

    def process_path(self, path: Path, parent_id=None):
        inode_type = InodeType.FOLDER if os.path.isdir(path) else InodeType.FILE

        try:
            inode = self.create_inode(path.name, inode_type, parent_id)

            if inode_type == InodeType.FOLDER:
                # Recursively upload files
                for child_path in os.listdir(path):
                    self.process_path(path / child_path, inode["id"])
            else:
                print(f"Uploading {path}")
                size = path.stat().st_size

                # Start upload of file
                with open(path, "rb") as f:
                    with tqdm(
                        total=size, unit="iB", unit_scale=True, unit_divisor=1024
                    ) as t:
                        reader_wrapper = CallbackIOWrapper(t.update, f, "read")

                        self.upload_object(inode["path"], size, reader_wrapper)

                        # Mark file as uploaded in backend
                        self.mark_file_uploaded(inode["id"])
        except InodeExistsException:
            logging.warning(f"{path} already exists!")

            inode = self.get_inode(path.name, parent_id)

            if inode_type == InodeType.FOLDER:
                # Recursively upload files
                for child_path in os.listdir(path):
                    self.process_path(path / child_path, inode["id"])
            else:
                print(f"Skipping upload of {path}")

    def get_user_id(self):
        access_token = self.token["access_token"]
        token_data = parse_token(access_token)
        return token_data["sub"]

    def upload_object(self, path: str, size: int, reader: BinaryIO):
        access_key, secret_key, session_token = self.get_storage_credentials()

        # Upload file to storage backend
        url = urlparse(get_option("storage", "endpoint"))
        minio = Minio(
            url.netloc,
            secure=url.scheme == "https",
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=config.get("storage", "region", fallback=None),
        )

        minio.put_object(
            get_option("storage", "bucket"),
            f"users/{self.get_user_id()}{path}/original",
            reader,
            size,
            content_type="application/pdf",
        )

    def get_storage_credentials(self):
        data = {
            "Action": "AssumeRoleWithWebIdentity",
            "Version": "2011-06-15",
            "DurationSeconds": "3600",
            "RoleSessionName": self.get_user_id(),
            "WebIdentityToken": self.token["access_token"],
        }

        # AWS requires RoleArn to be set, minio doesn't.
        try:
            identity_role = config.get("storage", "identity-role")
            if identity_role:
                data["RoleArn"] = identity_role
        except:
            pass

        # Get storage keys in exchange for JWT
        res = requests.post(get_option("storage", "sts-endpoint"), data=data)
        tree = ElementTree.fromstring(res.content)
        ns = {"s3": "https://sts.amazonaws.com/doc/2011-06-15/"}
        credentials = tree.find(
            "./s3:AssumeRoleWithWebIdentityResult/s3:Credentials", ns
        )

        return (
            credentials.find("s3:AccessKeyId", ns).text,
            credentials.find("s3:SecretAccessKey", ns).text,
            credentials.find("s3:SessionToken", ns).text,
        )


def parse_token(token):
    payload = token.split(".")[1].replace("-", "+").replace("_", "/")
    return json.loads(base64.b64decode(payload).decode("utf-8"))


def set_token(token):
    try:
        keyring.set_password("insight", "token", json.dumps(token))
    except:
        logging.warning("No suitable keyring backend, storing token as plaintext!")
        with open("token.json", "w") as fh:
            fh.write(json.dumps(token))


def get_token():
    try:
        token = keyring.get_password("insight", "token")
        return json.loads(token)
    except:
        with open("token.json", "r") as fh:
            logging.warning(
                "No suitable keyring backend, reading token from plaintext!"
            )
            return json.load(fh)


def delete_token():
    try:
        keyring.delete_password("insight", "token")
    except:
        logging.warning("No suitable keyring backend, removing plaintext token file")
        Path.unlink("token.json")


def get_client():
    return InsightClient(
        client_id=get_option("oidc", "client-id"),
        token=get_token(),
        auto_refresh_url=os.path.join(get_option("oidc", "endpoint"), "token"),
        auto_refresh_kwargs={
            "client_id": get_option("oidc", "client-id"),
        },
        token_updater=set_token,
    )


def authorize_device():
    res = requests.post(
        os.path.join(get_option("oidc", "endpoint"), "auth", "device"),
        data={"client_id": get_option("oidc", "client-id")},
    )
    body = res.json()

    try:
        webbrowser.get()
        webbrowser.open(body["verification_uri_complete"])
    except webbrowser.Error:
        print(f"Open {body['verification_uri_complete']} to authorize this device.")

    until_time = time.time() + body["expires_in"]
    while until_time > time.time():
        client = DeviceClient(get_option("oidc", "client-id"))
        try:
            session = OAuth2Session(client=client)
            token = session.fetch_token(
                client_id=get_option("oidc", "client-id"),
                token_url=os.path.join(get_option("oidc", "endpoint"), "token"),
                device_code=body["device_code"],
            )
            set_token(token)
            break
        except CustomOAuth2Error:
            time.sleep(body["interval"])
