# US Notify API

Cloned from the brilliant work of the team at [GOV.UK Notify](https://github.com/alphagov/notifications-api), cheers!

Contains:

- the public-facing REST API for US Notify, which teams can integrate with using [our clients](https://www.notifications.service.gov.uk/documentation) [DOCS ARE STILL UK]
- an internal-only REST API built using Flask to manage services, users, templates, etc (this is what the [admin app](http://github.com/18F/notifications-admin) talks to)
- asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc

## QUICKSTART
---
If you are the first on your team to deploy, set up AWS SES/SNS as instructed in the AWS setup section below.

Create .env file as described in the .env section below.

Install VS Code
Open VS Code and install the Remote-Containers plug-in from Microsoft.

Make sure your docker daemon is running (on OS X, this is typically accomplished by opening the Docker Desktop app)

Create the external docker network:

`docker network create notify-network`

Using the command palette (shift+cmd+p), search and select “Remote Containers: Open Folder in Container...”
When prompted, choose **devcontainer-api** folder (note: this is a *subfolder* of notification-api). This will startup the container in a new window (replacing the current one).

After this page loads, hit "show logs” in bottom-right. The first time this runs it will need to build the Docker image, which will likely take several minutes.

Select View->Open View..., then search/select “ports”. Await a green dot on the port view, then open a new terminal and run the web server:
`make run-flask`

Open another terminal and run the background tasks:
`make run-celery`

---
## Setting Up

### `.env` file

Create and edit a .env file, based on sample.env.

NOTE: when you change .env in the future, you'll need to rebuild the devcontainer for the change to take effect. Vscode _should_ detect the change and prompt you with a toast notification during a cached build. If not, you can find a manual rebuild in command pallette or just `docker rm` the notifications-api container.

Things to change:

- If you're not the first to deploy, only replace the aws creds, get these from team lead
- Replace `NOTIFICATION_QUEUE_PREFIX` with `local_dev_<your org>_`
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

### Postgres

Local postgres implementation is handled by [docker compose](https://github.com/18F/notifications-api/blob/main/docker-compose.devcontainer.yml)

### Redis

Local redis implementation is handled by [docker compose](https://github.com/18F/notifications-api/blob/main/docker-compose.devcontainer.yml)

## To test the application

```
# install dependencies, etc.
make bootstrap

make test
```

## To run a local OWASP scan

1. Run `make run-flask` from within the dev container.
2. On your host machine run:

```
docker run -v $(pwd):/zap/wrk/:rw --network="notify-network" -t owasp/zap2docker-weekly zap-api-scan.py -t http://dev:6011/_status -f openapi -c zap.conf
```

## To run scheduled tasks

```
# After scheduling some tasks, open a third terminal in your running devcontainer and run celery beat
make run-celery-beat
```

## To run one off tasks (Ignore for Quick Start)

Tasks are run through the `flask` command - run `flask --help` for more information. There are two sections we need to
care about: `flask db` contains alembic migration commands, and `flask command` contains all of our custom commands. For
example, to purge all dynamically generated functional test data, do the following:

Local (from inside the devcontainer)

```
flask command purge_functional_test_data -u <functional tests user name prefix>
```

Remote

```
cf run-task notify-api "flask command purge_functional_test_data -u <functional tests user name prefix>"
```

All commands and command options have a --help command if you need more information.

## Further documentation [DEPRECATED]

- [Writing public APIs](docs/writing-public-apis.md)
- [Updating dependencies](https://github.com/alphagov/notifications-manuals/wiki/Dependencies)
