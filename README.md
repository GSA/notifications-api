# GOV.UK Notify API

Contains:
- the public-facing REST API for GOV.UK Notify, which teams can integrate with using [our clients](https://www.notifications.service.gov.uk/documentation)
- an internal-only REST API built using Flask to manage services, users, templates, etc (this is what the [admin app](http://github.com/alphagov/notifications-admin) talks to)
- asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc

## Setting Up

### Python version

We run python 3.9 both locally and in production.

### psycopg2

[Follow these instructions on Mac M1 machines](https://github.com/psycopg/psycopg2/issues/1216#issuecomment-1068150544).

### AWS credentials

To run the API you will need appropriate AWS credentials. See the [Wiki](https://github.com/alphagov/notifications-manuals/wiki/aws-accounts#how-to-set-up-local-development) for more details.

### `environment.sh`

Creating and edit an environment.sh file.

```
echo "
export NOTIFY_ENVIRONMENT='development'

export MMG_API_KEY='MMG_API_KEY'
export FIRETEXT_API_KEY='FIRETEXT_ACTUAL_KEY'
export NOTIFICATION_QUEUE_PREFIX='YOUR_OWN_PREFIX'

export FLASK_APP=application.py
export FLASK_ENV=development
export WERKZEUG_DEBUG_PIN=off
"> environment.sh
```

Things to change:

* Replace `YOUR_OWN_PREFIX` with `local_dev_<first name>`.
* Run the following in the credentials repo to get the API keys.

```
notify-pass credentials/firetext
notify-pass credentials/mmg
```

### Secrets Detection

```
brew install detect-secrets # or pip install detect-secrets
detect-secrets scan
#review output of above, make sure none of the baseline entries are sensitive
detect-secrets scan > .secrets.baseline
#creates the baseline file
```

Ideally, you'll install `detect-secrets` so that it's accessible from any environment from which you _might_ commit. You can use `brew install` to make it available globally. You could also install via `pip install` inside a virtual environment, if you're sure you'll _only_ commit from that environment.

If you open .git/hooks/pre-commit you should see a simple bash script that runs the command below, reads the output and aborts before committing if detect-secrets finds a secret. You should be able to test it by staging a file with any high-entropy string like `"bblfwk3u4bt484+afw4avev5ae+afr4?/fa"` (it also has other ways to detect secrets, this is just the most straightforward to test). 

You can permit exceptions by adding an inline comment containing `pragma: allowlist secret`

The command that is actually run by the pre-commit hook is: `git diff --staged --name-only -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline`

You can also run against all tracked files staged or not: `git ls-files -z | xargs -0 detect-secrets-hook --baseline .secrets.baseline`

### Postgres

Install [Postgres.app](http://postgresapp.com/).

Currently the API works with PostgreSQL 11. After installation, open the Postgres app, open the sidebar, and update or replace the default server with a compatible version.

**Note:** you may need to add the following directory to your PATH in order to bootstrap the app.

```
export PATH=${PATH}:/Applications/Postgres.app/Contents/Versions/11/bin/
```

### Redis

To switch redis on you'll need to install it locally. On a Mac you can do:

```
# assuming you use Homebrew
brew install redis
brew services start redis
```

To use redis caching you need to switch it on with an environment variable:

```
export REDIS_ENABLED=1
```

##  To run the application

```
# install dependencies, etc.
make bootstrap

# run the web app
make run-flask

# run the background tasks
make run-celery

# run scheduled tasks (optional)
make run-celery-beat
```

We've had problems running Celery locally due to one of its dependencies: pycurl. Due to the complexity of the issue, we also support running Celery via Docker:

```
# install dependencies, etc.
make bootstrap-with-docker

# run the background tasks
make run-celery-with-docker

# run scheduled tasks
make run-celery-beat-with-docker
```

##  To test the application

```
# install dependencies, etc.
make bootstrap

make test
```

## To run one off tasks

Tasks are run through the `flask` command - run `flask --help` for more information. There are two sections we need to
care about: `flask db` contains alembic migration commands, and `flask command` contains all of our custom commands. For
example, to purge all dynamically generated functional test data, do the following:

Locally
```
flask command purge_functional_test_data -u <functional tests user name prefix>
```

On the server
```
cf run-task notify-api "flask command purge_functional_test_data -u <functional tests user name prefix>"
```

All commands and command options have a --help command if you need more information.

## Further documentation

- [Writing public APIs](docs/writing-public-apis.md)
- [Updating dependencies](https://github.com/alphagov/notifications-manuals/wiki/Dependencies)
