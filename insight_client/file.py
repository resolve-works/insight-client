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
    """List uploaded PDF files."""
    client = InsightClient()
    res = client.get(os.path.join(config.get("api", "endpoint"), "inodes"))
    print(res.text)


@file.command()
@click.argument("files", nargs=-1, type=click.Path(path_type=Path))
def upload(files):
    client = InsightClient()
    """Ingest PDF files"""
    for path in files:
        client.process_path(path)
