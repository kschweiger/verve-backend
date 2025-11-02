test-cov:
	uv run pytest  --cov=verve_backend tests --cov-report xml:cov.xml  --cov-report json --cov-report term --disable-warnings


