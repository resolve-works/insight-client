import click
from .file import file
from .oauth import authorize_device, delete_token, get_client
from configparser import ConfigParser
from .config import config_file, keys


@click.group()
def cli():
    """Insight command line client"""
    pass


cli.add_command(file)


@cli.command()
@click.option("--api-endpoint", help="Insight api root endpoint")
@click.option("--oidc-endpoint", help="Keycloak OIDC endpoint")
@click.option("--oidc-client-id", help="OIDC client ID")
@click.option("--oidc-client-secret", help="OIDC client secret")
@click.option(
    "--storage-sts-endpoint",
    help="S3 Object storage STS endpoint",
)
@click.option(
    "--storage-identity-role",
    help="S3 Object storage RoleArn",
)
@click.option("--storage-endpoint", help="S3 Object storage endpoint")
@click.option("--storage-bucket", help="S3 Object storage bucket")
@click.option("--storage-region", help="S3 Object storage region")
def configure(**kwargs):
    config = ConfigParser()
    for section in set(section for (section, _) in keys):
        config.add_section(section)

    for section, key in keys:
        value = kwargs[f"{section}_{key.replace('-', '_')}"]
        if value:
            config.set(section, key, value)

    config.write(open(config_file, "w"))


@cli.command()
def login():
    """Get access token from authentication provider."""
    authorize_device()


@cli.command()
def logout():
    """Remove authentication access token."""
    delete_token()


@cli.command()
def user_info():
    client = get_client()
    res = client.get(
        "https://secure.ftm.nl/realms/insight/account",
        headers={"Accept": "application/json"},
    )
    print(res.text)


@cli.command()
def user_groups():
    client = get_client()
    res = client.get(
        "https://secure.ftm.nl/realms/insight/account/groups",
        headers={"Accept": "application/json"},
    )
    print(res.text)
