import click
import logging
import os
from pathlib import Path
from .config import config
from .client import InsightClient


logging.basicConfig(level=logging.INFO)


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
        client.process_path(path, is_public=is_public)


@file.command()
@click.argument("id")
def delete(id):
    """Delete file or folder."""
    client = InsightClient()
    client.delete_inode(id)
