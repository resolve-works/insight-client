
test:
	OAUTHLIB_INSECURE_TRANSPORT=1 REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt poetry run pytest -s
