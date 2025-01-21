import click
import logging
import os
from tqdm import tqdm
from tqdm.utils import CallbackIOWrapper
from pathlib import Path
from .config import config
from .client import InsightClient, InodeExistsException, InodeType


logging.basicConfig(level=logging.INFO)


def process_path(
    client: InsightClient, path: Path, parent_id: str | None = None, is_public=False
):
    inode_type = InodeType.FOLDER if os.path.isdir(path) else InodeType.FILE

    if inode_type == InodeType.FOLDER:
        inode = client.find_or_create_folder(path.name, parent_id, is_public)

        # Recursively upload files
        for child_path in os.listdir(path):
            process_path(client, path / child_path, inode["id"], is_public)
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
        process_path(client, path, is_public=is_public)


@file.command()
@click.argument("id")
@click.argument("path", type=click.Path(path_type=Path))
def download(id, path):
    if not path.is_dir():
        raise Exception("Path should be a directory")
    client = InsightClient()
    data = client.get_inode(id=id)
    print(data)


@file.command()
@click.argument("id")
def delete(id):
    """Delete file or folder."""
    client = InsightClient()
    client.delete_inode(id)
