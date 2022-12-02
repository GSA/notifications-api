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

In addition to commit-triggered scans, the `daily_checks.yml` workflow runs the relevant dependency audits, static scan, and/or dynamic scans at 10am UTC each day. Developers will be notified of failures in daily scans by GitHub notifications.

## Manual testing

If you're checking out the system locally, you may want to create a user quickly.

`pipenv run flask command create-test-user`

This will run an interactive prompt to create a user, and then mark that user as active. *Use a real mobile number* if you want to log in, as the SMS auth code will be sent here.

## To run a local OWASP scan

1. Run `make run-flask` from within the dev container.
2. On your host machine run:

```
docker run -v $(pwd):/zap/wrk/:rw --network="notify-network" -t owasp/zap2docker-weekly zap-api-scan.py -t http://dev:6011/docs/openapi.yml -f openapi -c zap.conf
```

The equivalent command if you are running the API locally:

```
docker run -v $(pwd):/zap/wrk/:rw -t owasp/zap2docker-weekly zap-api-scan.py -t http://host.docker.internal:6011/docs/openapi.yml -f openapi -c zap.conf
```
