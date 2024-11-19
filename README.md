# Insight CLI

Simple command line interface for Insight

### Configuration

Before use, configure the insight CLI to point to your insight instance:

```
insight configure --help
```

After configuration, you can login with:

```
insight login
```

The insight configuration file can be found `$XDG_CONFIG_HOME/insight.conf` (default `~/.config/insight.conf`)

It is also possible to configure the client through environment variables:

```
INSIGHT_API_ENDPOINT
INSIGHT_OIDC_ENDPOINT
INSIGHT_OIDC_CLIENT_ID
INSIGHT_OIDC_CLIENT_SECRET
INSIGHT_STORAGE_STS_ENDPOINT
INSIGHT_STORAGE_ENDPOINT
INSIGHT_STORAGE_BUCKET
```

### Development

OAuth2Session does not trust our development certificates and doesn't connect to
insecure endpoints be default. We can overload that behaviour like so:

```
OAUTHLIB_INSECURE_TRANSPORT=1 REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt poetry run insight file list
```

### Releasing
