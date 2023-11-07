import click
from .pagestream import pagestream
from .oauth import authorize_device, delete_tokens


@click.group()
def cli():
    pass


@cli.command()
def login():
    authorize_device()


@cli.command()
def logout():
    delete_tokens()


cli.add_command(pagestream)
