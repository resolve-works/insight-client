# Insight client

Python client & command line interface for Insight

### CLI Configuration

Before use, configure the insight CLI to point to your insight instance:

```
insight configure --help
```

After configuration, you can login with:

```
insight login
```

The insight configuration file can be found `$XDG_CONFIG_HOME/insight.conf` (default `~/.config/insight.conf`)

It is also possible to configure the client through environment variables.

### Development

You can configure the CLI for development usage:

```
poetry run insight configure \
    --api-endpoint=http://localhost:8080 \
    --oidc-endpoint=https://localhost:8000/realms/insight/protocol/openid-connect \
    --oidc-client-id=insight \
    --storage-sts-endpoint=http://localhost:9000 \
    --storage-endpoint=http://localhost:9000 \
    --storage-bucket=insight \
    --storage-region=insight
```

OAuth2Session does not trust our development certificates and doesn't connect to
insecure endpoints be default. We can overload that behaviour like so:

```
OAUTHLIB_INSECURE_TRANSPORT=1 REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt poetry run insight file list
```
