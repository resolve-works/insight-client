import click
import logging
import os
import urllib
from typing import BinaryIO
from enum import Enum
from minio import Minio
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from pathlib import Path
from urllib.parse import urlparse
from .config import get_option, config
from .oauth import get_client, get_token, parse_token, get_storage_credentials


logging.basicConfig(level=logging.INFO)


class InodeType(Enum):
    FOLDER = "folder"
    FILE = "file"


class InodeExistsException(Exception):
    pass


def create_inode(name: str, inode_type: InodeType, parent_id: str | None = None):
    client = get_client()
    # Create inode model
    response = client.post(
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


def upload(path: str, size: int, reader: BinaryIO):
    access_token = get_token()["access_token"]
    token_data = parse_token(access_token)

    access_key, secret_key, session_token = get_storage_credentials()

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
        f"users/{token_data['sub']}{path}/original",
        reader,
        size,
        content_type="application/pdf",
    )


def process_path(path, parent_id=None):
    client = get_client()
    inode_type = InodeType.FOLDER if os.path.isdir(path) else InodeType.FILE

    try:
        inode = create_inode(path.name, inode_type, parent_id)

        if inode_type == InodeType.FOLDER:
            # Recursively upload files
            for child_path in os.listdir(path):
                process_path(path / child_path, inode["id"])
        else:
            print(f"Uploading {path}")
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

                    upload(inode["path"], size, reader_wrapper)

                    # Mark file as uploaded in backend
                    res = client.patch(
                        os.path.join(get_option("api", "endpoint"), "inodes")
                        + f"?id=eq.{inode['id']}",
                        data={"is_uploaded": True},
                    )
                    if res.status_code != 204:
                        print("derp")
                        logging.error(res.text)
                        exit(1)
    except InodeExistsException:
        logging.warning(f"{path} already exists!")

        url = os.path.join(get_option("api", "endpoint"), "inodes")
        params = {"name": f"eq.{path.name}"}
        if parent_id:
            params["parent_id"] = f"eq.{parent_id}"

        res = client.get(url + "?" + urllib.parse.urlencode(params))
        inode = res.json()[0]

        if inode_type == InodeType.FOLDER:
            # Recursively upload files
            for child_path in os.listdir(path):
                process_path(path / child_path, inode["id"])
        else:
            print(f"Skipping upload of {path}")


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


@file.command()
@click.argument("files", nargs=-1, type=click.Path(path_type=Path))
def upload(files):
    """Ingest PDF files"""
    for path in files:
        process_path(path)
