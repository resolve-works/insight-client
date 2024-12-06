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
from oauthlib.oauth2 import DeviceClient, BackendApplicationClient
from oauthlib.oauth2.rfc6749.errors import CustomOAuth2Error, TokenExpiredError
from requests_oauthlib import OAuth2Session
from enum import Enum
from urllib.parse import urlparse, urlencode
from typing import BinaryIO
from minio import Minio
from minio.commonconfig import Tags
from .config import config

logging.getLogger().setLevel(logging.INFO)


class InodeType(Enum):
    FOLDER = "folder"
    FILE = "file"


class InodeExistsException(Exception):
    pass


class InsightClient(OAuth2Session):
    token_url = os.path.join(config.get("oidc", "endpoint"), "token")
    client_id = config.get("oidc", "client-id")
    client_secret = config.get("oidc", "client-secret", fallback=None)

    storage_token: dict | None = None

    def __init__(self):
        token = get_initial_token(self.token_url, self.client_id, self.client_secret)

        if "refresh_token" in token:
            # Remember token as we can use it to refresh next time
            set_token(token)
            super().__init__(client_id=self.client_id, token=token)
        else:
            super().__init__(client=BackendApplicationClient(client_id=self.client_id))

    def fetch_token(self, *args, **kwargs):
        token = super().fetch_token(*args, **kwargs)
        self.refresh_storage_credentials()
        return token

    def refresh_token(self):
        if "refresh_token" in self.token:
            # Refresh token & storage creds
            super().refresh_token(
                self.token_url,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            self.refresh_storage_credentials()
            # Remember token as we can use it later to refresh
            set_token(self.token)
            return self.token
        else:
            return self.fetch_token(self.token_url, client_secret=self.client_secret)

    def refresh_storage_credentials(self):
        data = {
            "Action": "AssumeRoleWithWebIdentity",
            "Version": "2011-06-15",
            "DurationSeconds": "3600",
            "RoleSessionName": self.get_user_id(),
            "WebIdentityToken": self.token["access_token"],
        }

        # AWS requires RoleArn to be set, minio doesn't.
        identity_role = config.get("storage", "identity-role", fallback=None)
        if identity_role:
            data["RoleArn"] = identity_role

        # Get storage keys in exchange for JWT
        response = requests.post(config.get("storage", "sts-endpoint"), data=data)
        tree = ElementTree.fromstring(response.content)
        ns = {"s3": "https://sts.amazonaws.com/doc/2011-06-15/"}
        credentials = tree.find(
            "./s3:AssumeRoleWithWebIdentityResult/s3:Credentials", ns
        )

        self.storage_token = {
            "access_key": credentials.find("s3:AccessKeyId", ns).text,
            "secret_key": credentials.find("s3:SecretAccessKey", ns).text,
            "session_token": credentials.find("s3:SessionToken", ns).text,
        }

    def request(self, method: str, url: str, *args, **kwargs):
        try:
            response = super().request(method, url, *args, **kwargs)
            # When API returns Unauthorized, retry with new token
            if response.status_code == 401 and url.startswith(
                config.get("api", "endpoint")
            ):
                raise TokenExpiredError()
            return response
        except TokenExpiredError:
            self.refresh_token()
            return super().request(method, url, *args, **kwargs)

    def create_inode(
        self,
        name: str,
        inode_type: InodeType,
        parent_id: str | None = None,
        is_public=False,
    ):
        # Create inode model
        response = self.post(
            os.path.join(config.get("api", "endpoint"), "inodes"),
            data={
                "name": name,
                "type": inode_type.value,
                "parent_id": parent_id,
                "is_public": is_public,
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

    def get_inodes(self, parent_id: str | None = None):
        url = os.path.join(config.get("api", "endpoint"), "inodes")
        params = {}
        if parent_id:
            params["parent_id"] = f"eq.{parent_id}"

        response = self.get(url + "?" + urlencode(params))
        return response.json()

    def get_inode(self, name: str, parent_id: str | None = None):
        url = os.path.join(config.get("api", "endpoint"), "inodes")
        params = {"name": f"eq.{name}"}
        if parent_id:
            params["parent_id"] = f"eq.{parent_id}"

        response = self.get(
            url + "?" + urlencode(params),
            headers={"Accept": "application/vnd.pgrst.object+json"},
        )
        return response.json()

    def delete_inode(self, id: str):
        url = os.path.join(config.get("api", "endpoint"), "inodes")
        params = {"id": f"eq.{id}"}
        response = self.delete(url + "?" + urlencode(params))
        if response.status_code != 204:
            raise Exception(response.json()["message"])

    def create_folder(self, name: str, parent_id: str | None = None, is_public=False):
        try:
            return self.create_inode(name, InodeType.FOLDER, parent_id, is_public)
        except InodeExistsException:
            return self.get_inode(name, parent_id)

    def create_file(
        self,
        name: str,
        size: int,
        reader: BinaryIO,
        parent_id: str | None = None,
        is_public=False,
    ):
        try:
            # Only upload when inode didn't exist yet
            inode = self.create_inode(name, InodeType.FILE, parent_id, is_public)
            self.upload_object(inode["path"], size, reader, is_public)
            self.mark_file_uploaded(inode["id"])

            return inode
        except InodeExistsException:
            return self.get_inode(name, parent_id)

    def mark_file_uploaded(self, id: str):
        # Mark file as uploaded in backend
        response = self.patch(
            os.path.join(config.get("api", "endpoint"), "inodes") + f"?id=eq.{id}",
            data={"is_uploaded": True},
        )
        if response.status_code != 204:
            data = response.json()
            raise Exception(data["message"])

    def process_path(self, path: Path, parent_id: str | None = None, is_public=False):
        inode_type = InodeType.FOLDER if os.path.isdir(path) else InodeType.FILE

        if inode_type == InodeType.FOLDER:
            inode = self.create_folder(path.name, parent_id, is_public)

            # Recursively upload files
            for child_path in os.listdir(path):
                self.process_path(path / child_path, inode["id"], is_public)
        else:
            size = path.stat().st_size

            try:
                # Only upload when inode didn't exist yet
                inode = self.create_inode(
                    path.name, InodeType.FILE, parent_id, is_public
                )

                logging.info(f"Uploading {path}")
                with open(path, "rb") as f:
                    with tqdm(
                        total=size, unit="iB", unit_scale=True, unit_divisor=1024
                    ) as t:
                        reader_wrapper = CallbackIOWrapper(t.update, f, "read")
                        self.upload_object(
                            inode["path"], size, reader_wrapper, is_public
                        )
                self.mark_file_uploaded(inode["id"])
            except InodeExistsException:
                logging.info(f"File exists: {path}")

    def get_user_id(self):
        payload = (
            self.token["access_token"].split(".")[1].replace("-", "+").replace("_", "/")
        )
        token_data = json.loads(base64.b64decode(payload + "==").decode("utf-8"))
        return token_data["sub"]

    def upload_object(self, path: str, size: int, reader: BinaryIO, is_public=False):
        # Upload file to storage backend
        url = urlparse(config.get("storage", "endpoint"))
        minio = Minio(
            url.netloc,
            secure=url.scheme == "https",
            access_key=self.storage_token["access_key"],
            secret_key=self.storage_token["secret_key"],
            session_token=self.storage_token["session_token"],
            region=config.get("storage", "region", fallback=None),
        )

        object_path = f"users/{self.get_user_id()}{path}"

        minio.put_object(
            config.get("storage", "bucket"),
            object_path,
            reader,
            size,
            content_type="application/pdf",
        )

        if is_public:
            tags = Tags.new_object_tags()
            tags["is_public"] = str(is_public)
            minio.set_object_tags(config.get("storage", "bucket"), object_path, tags)


def get_initial_token(token_url: str, client_id: str, client_secret: str | None = None):
    # Use existing token if it's set
    try:
        token = get_token()

        session = OAuth2Session(client_id=config.get("oidc", "client-id"), token=token)
        return session.refresh_token(
            token_url=token_url, client_id=client_id, client_secret=client_secret
        )
    except:
        pass

    # No token yet, assume we are a BackendApplicationClient
    try:
        session = OAuth2Session(client=BackendApplicationClient(client_id=client_id))
        return session.fetch_token(
            token_url=token_url, client_id=client_id, client_secret=client_secret
        )
    except:
        pass

    # We're also not a BackendApplicationClient, try to do device authorization
    logging.info("No valid device credentials found. Attempting authorization.")
    response = requests.post(
        os.path.join(config.get("oidc", "endpoint"), "auth", "device"),
        data={"client_id": client_id},
    )
    body = response.json()

    try:
        logging.info(
            f"Open {body['verification_uri_complete']} to authorize this device."
        )
        webbrowser.get()
        webbrowser.open(body["verification_uri_complete"])
    except webbrowser.Error:
        pass

    until_time = time.time() + body["expires_in"]
    while until_time > time.time():
        try:
            session = OAuth2Session(client=DeviceClient(client_id))
            return session.fetch_token(
                client_id=client_id,
                token_url=token_url,
                device_code=body["device_code"],
            )
        except CustomOAuth2Error:
            time.sleep(body["interval"])


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


# Make sure to delete it all
def delete_token():
    try:
        keyring.delete_password("insight", "token")
    except:
        pass

    try:
        Path.unlink("token.json")
    except:
        pass
