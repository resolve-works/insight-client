import click
import logging
import os
from pathlib import Path
from .config import get_option
from .client import get_client


logging.basicConfig(level=logging.INFO)


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
    client = get_client()
    """Ingest PDF files"""
    for path in files:
        client.process_path(path)
