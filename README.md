# Insight client

Python client & command line interface for Insight

### Client Configuration

Before use, insight-client has to be configured. Configuration includes
information about the OIDC provider, insight API and S3 storage backend. When
you provide the client with a `oidc.client-secret`, the
client will assume it's being used with a Service Account Role OIDC
configuration. When no secret is provided it will try to authenticate using a
Device Authorization Grant.

```
insight configure --help
```

The insight configuration file can be found `$XDG_CONFIG_HOME/insight.conf` (default `~/.config/insight.conf`)

It is also possible to configure the client through environment variables:

```
INSIGHT_API_ENDPOINT
INSIGHT_OIDC_ENDPOINT
INSIGHT_OIDC_CLIENT_ID
INSIGHT_OIDC_CLIENT_SECRET
INSIGHT_STORAGE_STS_ENDPOINT
INSIGHT_STORAGE_IDENTITY_ROLE
INSIGHT_STORAGE_ENDPOINT
INSIGHT_STORAGE_BUCKET
INSIGHT_STORAGE_REGION
```

### Development

You can configure the CLI for the default development setup like so, this will
make use of the Device Authorization Grant:

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
