import json
import time
import webbrowser
import requests
import logging
import os
import base64
import json
from xml.etree import ElementTree
from pathlib import Path
from oauthlib.oauth2 import DeviceClient
from oauthlib.oauth2.rfc6749.errors import CustomOAuth2Error
from requests_oauthlib import OAuth2Session
from .config import get_option, config

logging.basicConfig(level=logging.ERROR)


def parse_token(token):
    payload = token.split(".")[1].replace("-", "+").replace("_", "/")
    return json.loads(base64.b64decode(payload).decode("utf-8"))


def set_token(token):
    with open("token.json", "w") as fh:
        fh.write(json.dumps(token))


def get_token():
    with open("token.json", "r") as fh:
        return json.load(fh)


def delete_token():
    Path.unlink("token.json")


def get_client():
    return OAuth2Session(
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
            token = OAuth2Session(client=client).fetch_token(
                client_id=get_option("oidc", "client-id"),
                token_url=os.path.join(get_option("oidc", "endpoint"), "token"),
                device_code=body["device_code"],
            )
            set_token(token)
            break
        except CustomOAuth2Error:
            time.sleep(body["interval"])


def get_storage_credentials():
    access_token = get_token()["access_token"]
    token_data = parse_token(access_token)

    data = {
        "Action": "AssumeRoleWithWebIdentity",
        "Version": "2011-06-15",
        "DurationSeconds": "3600",
        "RoleSessionName": token_data["sub"],
        "WebIdentityToken": access_token,
    }

    try:
        identity_role = config.get("storage", "identity-role")
        if identity_role:
            data["RoleArn"] = identity_role
    except:
        pass

    # Get storage keys in exchange for JWT
    res = requests.post(
        get_option("storage", "sts-endpoint"),
        data=data,
    )

    tree = ElementTree.fromstring(res.content)
    ns = {"s3": "https://sts.amazonaws.com/doc/2011-06-15/"}
    credentials = tree.find("./s3:AssumeRoleWithWebIdentityResult/s3:Credentials", ns)

    return (
        credentials.find("s3:AccessKeyId", ns).text,
        credentials.find("s3:SecretAccessKey", ns).text,
        credentials.find("s3:SessionToken", ns).text,
    )
