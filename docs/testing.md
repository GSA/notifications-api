# Testing

```
# install dependencies, etc.
make bootstrap

make test
```

This will run:
- flake8 for code styling
- isort for import styling
- pytest for the test suite

On GitHub, in addition to these tests, we run:
- bandit for code security
- pip-audit for dependency vulnerabilities
- OWASP for dynamic scanning

## CI testing

We're using GitHub Actions. See [/.github](../.github/) for the configuration.

## To run a local OWASP scan

1. Run `make run-flask` from within the dev container.
2. On your host machine run:

```
docker run -v $(pwd):/zap/wrk/:rw --network="notify-network" -t owasp/zap2docker-weekly zap-api-scan.py -t http://dev:6011/_status -f openapi -c zap.conf
```