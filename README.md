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

### `.env` file

Create and edit a .env file, based on sample.env

Things to change:

- Replace `YOUR_OWN_PREFIX` with `local_dev_<first name>`
- Replace `NOTIFY_EMAIL_DOMAIN` with the domain your emails will come from (i.e. the "origination email" in your SES project)
- Replace `SECRET_KEY` and `DANGEROUS_SALT` with high-entropy secret values
- Set up AWS SES and SNS as indicated in next section (AWS Setup), fill in missing AWS env vars

### AWS Setup

**Steps to prepare SES**

1. Go to SES console for \$AWS_REGION and create new origin and destination emails. AWS will send a verification via email which you'll need to complete.
2. Find and replace instances in the repo of "testsender", "testreceiver" and "dispostable.com", with your origin and destination email addresses, which you verified in step 1 above.

TODO: create env vars for these origin and destination email addresses for the root service, and create new migrations to update postgres seed fixtures

**Steps to prepare SNS**

1. Go to Pinpoints console for \$AWS_PINPOINT_REGION and choose "create new project", then "configure for sms"
2. Tick the box at the top to enable SMS, choose "transactional" as the default type and save
3. In the lefthand sidebar, go the "SMS and Voice" (bottom) and choose "Phone Numbers"
4. Under "Number Settings" choose "Request Phone Number"
5. Choose Toll-free number, tick SMS, untick Voice, choose "transactional", hit next and then "request"
6. Go to SNS console for \$AWS_PINPOINT_REGION, look at lefthand sidebar under "Mobile" and go to "Text Messaging (SMS)"
7. Scroll down to "Sandbox destination phone numbers" and tap "Add phone number" then follow the steps to verify (you'll need to be able to retrieve a code sent to each number)

At this point, you _should_ be able to complete both the email and phone verification steps of the Notify user sign up process! 🎉

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

### Postgres [DEPRECATED]

Install [Postgres.app](http://postgresapp.com/).

Currently the API works with PostgreSQL 11. After installation, open the Postgres app, open the sidebar, and update or replace the default server with a compatible version.

**Note:** you may need to add the following directory to your PATH in order to bootstrap the app.

```
export PATH=${PATH}:/Applications/Postgres.app/Contents/Versions/11/bin/
```

### Redis [DEPRECATED]

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

## To run the application

```
# set up AWS SES/SNS as instructed above

# create .env file as instructed above

# download vscode and install the Remote-Containers plug-in from Microsoft

# create the external docker network
docker network create notify-network

# Using the command pallette, search "Remote Containers: Open folder in project" and choose devcontainer-api, then wait for docker to build

# Open a terminal in vscode and run the web server
make run-flask

# Open another terminal in vscode and run the background tasks
make run-celery

# Open a third terminal in vscode and run scheduled tasks (optional)
make run-celery-beat
```

## To test the application

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
