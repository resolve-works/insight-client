import click
import requests
import logging
import os
from minio import Minio
from xml.etree import ElementTree
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from pathlib import Path
from urllib.parse import urlparse
from .config import get_option
from .oauth import get_client, get_token


@click.group()
def file():
    """Manage PDF files."""
    pass


@file.command()
def list():
    """List uploaded PDF files."""
    client = get_client()
    res = client.get(os.path.join(get_option("api", "endpoint"), "inodes"))
    print(res.text)


def load_file(path):
    progressbar = tqdm(
        desc=path.name,
        total=path.stat().st_size,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
    )

    for chunk in iter(open(path, "rb")):
        progressbar.update(len(chunk))
        yield chunk


def upload_file(path, parent_id=None):
    client = get_client()
    is_folder = os.path.isdir(path)

    # Create inode model
    res = client.post(
        os.path.join(get_option("api", "endpoint"), "inodes"),
        data={
            "name": path.name,
            "type": "folder" if is_folder else "file",
            "parent_id": parent_id,
        },
        headers={"Prefer": "return=representation"},
    )

    if res.status_code != 201:
        logging.error(res.text)
        exit(1)

    inode = res.json()[0]

    if is_folder:
        # Recursively upload files
        for child_path in os.listdir(path):
            upload_file(path / child_path, inode["id"])
    else:
        # TODO - Only upload PDF

        size = path.stat().st_size

        # Start upload of file
        with open(path, "rb") as f:
            with tqdm(
                desc=path.name,
                total=size,
                unit="iB",
                unit_scale=True,
                unit_divisor=1024,
            ) as t:
                reader_wrapper = CallbackIOWrapper(t.update, f, "read")
                access_token = get_token()["access_token"]

                # Get storage keys in exchange for JWT
                res = requests.post(
                    get_option("storage", "sts-endpoint"),
                    data={
                        "Action": "AssumeRoleWithWebIdentity",
                        "Version": "2011-06-15",
                        "DurationSeconds": "3600",
                        "WebIdentityToken": access_token,
                    },
                )

                tree = ElementTree.fromstring(res.content)
                ns = {"s3": "https://sts.amazonaws.com/doc/2011-06-15/"}
                credentials = tree.find(
                    "./s3:AssumeRoleWithWebIdentityResult/s3:Credentials", ns
                )

                # Upload file to storage backend
                url = urlparse(get_option("storage", "endpoint"))
                minio = Minio(
                    url.netloc,
                    secure=url.scheme == "https",
                    access_key=credentials.find("s3:AccessKeyId", ns).text,
                    secret_key=credentials.find("s3:SecretAccessKey", ns).text,
                    session_token=credentials.find("s3:SessionToken", ns).text,
                    region="insight",
                )

                minio.put_object(
                    get_option("storage", "bucket"),
                    f"/users/{inode['owner_id']}{inode['path']}/original",
                    reader_wrapper,
                    size,
                    content_type="application/pdf",
                )

                # Mark file as uploaded in backend
                res = client.patch(
                    os.path.join(get_option("api", "endpoint"), "inodes")
                    + f"?id=eq.{inode['id']}",
                    data={"is_uploaded": True},
                )
                if res.status_code != 204:
                    logging.error(res.text)
                    exit(1)


def upload_directory(path, parent_id=None):
    for child_path in os.listdir(path):
        print(child_path)
        pass


@file.command()
@click.argument("files", nargs=-1, type=click.Path(path_type=Path))
def upload(files):
    """Ingest PDF files"""
    for path in files:
        upload_file(path)
