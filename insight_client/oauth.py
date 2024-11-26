import json
import time
import keyring
import webbrowser
import requests
import logging
import os
import base64
import json
from pathlib import Path
from oauthlib.oauth2 import DeviceClient
from oauthlib.oauth2.rfc6749.errors import CustomOAuth2Error
from requests_oauthlib import OAuth2Session
from .config import get_option

logging.basicConfig(level=logging.ERROR)


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
        return json.loads(token) if token is not None else None
    except:
        try:
            with open("token.json", "r") as fh:
                logging.warning(
                    "No suitable keyring backend, reading token from plaintext!"
                )
                return json.load(fh)
        except FileNotFoundError:
            return None


def delete_token():
    try:
        keyring.delete_password("insight", "token")
    except:
        logging.warning("No suitable keyring backend, removing plaintext token file")
        Path.unlink("token.json")
        return None


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
