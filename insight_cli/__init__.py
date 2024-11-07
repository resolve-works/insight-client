import click
from .file import file
from .oauth import authorize_device, delete_token, get_client
from configparser import ConfigParser
from .config import config_file


@click.group()
def cli():
    """Insight command line client"""
    pass


cli.add_command(file)


@cli.command()
@click.option("--api-endpoint", prompt="api.endpoint", help="Insight api root endpoint")
@click.option("--oidc-endpoint", prompt="oidc.endpoint", help="Keycloak OIDC endpoint")
@click.option("--oidc-client-id", prompt="oidc.client-id", help="OIDC client ID")
@click.option(
    "--storage-sts-endpoint",
    prompt="storage.sts-endpoint",
    help="S3 Object storage STS endpoint",
)
@click.option(
    "--storage-endpoint", prompt="storage.endpoint", help="S3 Object storage endpoint"
)
@click.option(
    "--storage-bucket", prompt="storage.bucket", help="S3 Object storage bucket"
)
def configure(
    api_endpoint,
    oidc_endpoint,
    oidc_client_id,
    storage_sts_endpoint,
    storage_endpoint,
    storage_bucket,
):
    config = ConfigParser()
    config.add_section("api")
    config.add_section("oidc")
    config.add_section("storage")
    config.set("api", "endpoint", api_endpoint)
    config.set("oidc", "endpoint", oidc_endpoint)
    config.set("oidc", "client-id", oidc_client_id)
    config.set("storage", "sts-endpoint", storage_sts_endpoint)
    config.set("storage", "endpoint", storage_endpoint)
    config.set("storage", "bucket", storage_bucket)
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
