import click
import logging
import os
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from pathlib import Path
from .config import config
from .client import InsightClient, InodeExistsException, InodeType


logging.basicConfig(level=logging.INFO)


def upload_path(
    client: InsightClient, path: Path, parent_id: str | None = None, is_public=False
):
    inode_type = InodeType.FOLDER if os.path.isdir(path) else InodeType.FILE

    if inode_type == InodeType.FOLDER:
        inode = client.find_or_create_folder(path.name, parent_id, is_public)

        # Recursively upload files
        for child_path in os.listdir(path):
            upload_path(client, path / child_path, inode["id"], is_public)
    else:
        size = path.stat().st_size

        with open(path, "rb") as f:
            with tqdm(total=size, unit="iB", unit_scale=True, unit_divisor=1024) as t:
                reader_wrapper = CallbackIOWrapper(t.update, f, "read")
                try:
                    client.upload_file(
                        path.name, size, reader_wrapper, parent_id, is_public
                    )
                except InodeExistsException:
                    logging.info(f"File exists: {path}")


def download_inode(client: InsightClient, data: dict, path: Path):
    # Get parent path so we can strip it from inodes path
    parent_path = "/"
    if data["parent_id"] is not None:
        parent = client.get_inode(id=data["parent_id"])
        parent_path = parent["path"]

    # Get path of inode relative to parent
    relative_inode_path = data["path"][len(parent_path) :].lstrip("/")
    path = path / relative_inode_path

    if data["type"] == "file":
        logging.info(f"Downloading: {path}")
        # Download file to local disk
        object_path = f"users/{data["owner_id"]}{data["path"]}"
        client.download_object(object_path, path)
    elif data["type"] == "folder":
        # Check if there's children
        children = client.get_inodes(parent_id=data["id"])

        # Create folder and download child inodes
        if len(children) > 0:
            if not os.path.exists(path):
                os.makedirs(path)

            for child in children:
                download_inode(client, child, path)
    else:
        raise Exception("Unknown inode type")


@click.group()
def file():
    """Manage PDF files."""
    pass


@file.command()
def list():
    """List uploaded files and folders."""
    client = InsightClient()
    res = client.get(os.path.join(config.get("api", "endpoint"), "inodes"))
    print(res.text)


@file.command()
@click.argument("files", nargs=-1, type=click.Path(path_type=Path))
@click.option("--is-public", is_flag=True)
def upload(files, is_public):
    client = InsightClient()
    """Ingest PDF files"""
    for path in files:
        upload_path(client, path, is_public=is_public)


@file.command()
@click.argument("id")
@click.argument("path", type=click.Path(path_type=Path))
def download(id, path):
    if not path.is_dir():
        raise Exception("Path should be a directory")
    client = InsightClient()
    data = client.get_inode(id=id)
    download_inode(client, data, path)


@file.command()
@click.argument("id")
def delete(id):
    """Delete file or folder."""
    client = InsightClient()
    client.delete_inode(id)
