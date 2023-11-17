# US Notify API

This project is the core of [Notify](https://notifications-admin.app.cloud.gov/).
It's cloned from the brilliant work of the team at
[GOV.UK Notify](https://github.com/alphagov/notifications-api), cheers!

This repo contains:

- A public-facing REST API for Notify, which teams can integrate with using
 [API clients built by UK](https://www.notifications.service.gov.uk/documentation)
- An internal-only REST API built using Flask to manage services, users,
  templates, etc., which the [admin UI](http://github.com/18F/notifications-admin)
  talks to)
- Asynchronous workers built using Celery to put things on queues and read them
  off to be processed, sent to providers, updated, etc.

Our other repositories are:

- [notifications-admin](https://github.com/GSA/notifications-admin)
- [notifications-utils](https://github.com/GSA/notifications-utils)
- [us-notify-compliance](https://github.com/GSA/us-notify-compliance/)
- [notify-python-demo](https://github.com/GSA/notify-python-demo)

## Before You Start

You will need the following items:

- An active cloud.gov account with the correct permissions - speak with your
  onboarding buddy for help with
  [setting up an account](https://cloud.gov/sign-up/) (requires a `.mil`,
  `.gov`, or `.fed.us` email address) and getting access to the
  `notify-local-dev` and `notify-staging` spaces.
- Admin priviliges and SSH access on your machine; you may need to work with
  your organization's IT support staff if you're not sure or don't currently
  have this access.

## Local Environment Setup

This project currently works with these major versions of the following main
components:

- Python 3.9.x
- PostgreSQL 15.x (version 12.x is used in the hosted environments)

These instructions will walk you through how to set your machine up with all of
the required tools for this project.

### Project Pre-Requisite Setup

On MacOS, using [Homebrew](https://brew.sh/) for package management is highly
recommended. This helps avoid some known installation issues. Start by following
the installation instructions on the Homebrew homepage.

**Note:** You will also need Xcode or the Xcode Command Line Tools installed. The
quickest way to do this is is by installing the command line tools in the shell:

```sh
xcode-select –-install
```

#### Homebrew Setup

If this is your first time installing Homebrew on your machine, you may need to
add its binaries to your system's `$PATH` environment variable so that you can
use the `brew` command. Try running `brew help` to see if Homebrew is
recognized and runs properly. If that fails, then you'll need to add a
configuration line to wherever your `$PATH` environment variable is set.

Your system `$PATH` environment variable is likely set in one of these
locations:

For BASH shells:
- `~/.bashrc`
- `~/.bash_profile`
- `~/.profile`

For ZSH shells:
- `~/.zshrc`
- `~/.zprofile`

There may be different files that you need to modify for other shell
environments.

Which file you need to modify depends on whether or not you are running an
interactive shell or a login shell
(see [this Stack Overflow post](https://stackoverflow.com/questions/18186929/what-are-the-differences-between-a-login-shell-and-interactive-shell)
for an explanation of the differences).  If you're still not sure, please ask
the team for help!

Once you determine which file you'll need to modify, add these lines before any
lines that add or modify the `$PATH` environment variable; near or at the top
of the file is appropriate:

```sh
# Homebrew setup
eval "$(/opt/homebrew/bin/brew shellenv)"
```

This will make sure Homebrew gets setup correctly. Once you make these changes,
either start a new shell session or source the file
(`source ~/.FILE-YOU-MODIFIED`) you modified to have your system recognize the
changes.

Verify that Homebrew is now working by trying to run `brew help` again.

### System-Level Package Installation

There are several packages you will need to install for your system in order to
get the app running (and these are good to have in general for any software
development).

Start off with these packages since they're quick and don't require additional
configuration after installation to get working out of the box:

- [jq](https://stedolan.github.io/jq/) - for working with JSON in the command
  line
- [git](https://git-scm.com/) - for version control management
- [tfenv](https://github.com/tfutils/tfenv) - for managing
  [Terraform](https://www.terraform.io/) installations
- [cf-cli@8](https://docs.cloudfoundry.org/cf-cli/install-go-cli.html) - for
  working with a Cloud Foundry platform (e.g., cloud.gov)
- [redis](https://redis.io/) - required as the backend for the API's
  asynchronous job processing
- [vim](https://www.vim.org/) - for editing files more easily in the command
  line

You can install them by running the following:

```sh
brew install jq git tfenv cloudfoundry/tap/cf-cli@8 redis vim
```

#### Terraform Installation

As a part of the installation above, you just installed `tfenv` to manage
Terraform installations. This is great, but you still need to install Terraform
itself, which can be done with this command:

```sh
tfenv install latest:^1.4.0
```

_NOTE: This project currently uses the latest `1.4.x release of Terraform._

#### Python Installation

Now we're going to install a tool to help us manage Python versions on our
system.  First, we'll install [pyenv](https://github.com/pyenv/pyenv) with
Homebrew:

```sh
brew install pyenv
```

When that finishes installing, you'll need to make another adjustment in the
file that you adjusted for your `$PATH` environment variable and Homebrew's
setup. Open the file, and add these lines to it:

```
# pyenv setup
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

Once again, start a new shell session or source the file in your current shell
session to make the changes take effect.

Now we're ready to install the Python version we need with `pyenv`, like so:

```sh
pyenv install 3.9
```

This will install the latest version of Python 3.9.

_NOTE: This project currently runs on Python 3.9.x._

#### Python Dependency Installation

Lastly, we need to install the tool we use to manage Python dependencies within
the project, which is [poetry](https://python-poetry.org/).

Visit the
[official installer instructions page](https://python-poetry.org/docs/#installing-with-the-official-installer)
and follow the steps to install Poetry directly with the script.

This will ensure `poetry` doesn't conflict with any project virtual environments
and can update itself properly.

#### PostgreSQL installation

We now need to install a database - this project uses PostgreSQL, and Homebrew
requires a version number to be included with it when installing it:

```sh
brew install postgresql@15
```

_NOTE: This project currently works with PostgreSQL version 15.x; version 12.x is currently used in our hosted environments._

You'll now need to modify (or create, if it doesn't already exist) the `$PATH`
environment variable to include the PostgreSQL binaries. Open the file you have
worked with before to adjust your shell environment with the previous steps and
do one of the following:

If you already have a line that modifies the `$PATH` environment variable, just
add this path into the existing string:

```
/opt/homebrew/opt/postgresql@15/bin
```

If you don't have a line for your `$PATH` environment variable, add it in like
this, which will include the PostgreSQL binaries:

```
export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH
```

_NOTE: You don't want to overwrite your existing `$PATH` environment variable! Hence the reason why it is included on the end like this; paths are separated by a colon._

#### Starting PostgreSQL and Redis

With both PostgreSQL and Redis installed, you now need to start the services.
Run this command so that they're available at all times going forward on your
machine:

```sh
brew services start postgresql@15
brew services start redis
```

If they're already running, you can run this command instead to make sure the
latest updates are applied to both services:

```sh
brew services restart postgresql@15
brew services restart redis
```

### First-Time Project Setup

Once all of pre-requisites for the project are installed and you have a
cloud.gov account, you can now set up the API project and get things running
locally!

First, clone the respository in the directory of your choosing on your machine:

```sh
git clone git@github.com:GSA/notifications-api.git
```

Now go into the project directory (`notifications-api` by default) and set the
local Python version, like this (assumes version Python `3.9.18` is what is
installed on your machine):

```sh
cd notifications-api
pyenv local 3.9.18
```

_If you're not sure which version of Python was installed with `pyenv`, you can check by running `pyenv versions` and it'll list everything available currently._

Now [log into cloud.gov](https://cloud.gov/docs/getting-started/setup/#set-up-the-command-line)
in the command line by using this command:

```sh
cf login -a api.fr.cloud.gov --sso
```

_REMINDER: Ensure you have access to the `notify-local-dev` and `notify-staging` spaces in cloud.gov_

Now run the development Terraform setup by navigating to the development
folder and running the script in it:

```sh
cd terraform/development
./run.sh
```

In addition to some infrastructure setup, this will also create a local `.env`
file for you in the project's root directory, which will include a handful of
project-specific environment variables.

Lastly, if you didn't already start PostgreSQL and Redis above, be sure to do
so now:

```sh
brew services start postgresql@15
brew services start redis
```

## Running the Project and Routine Maintenance

The first time you run the project you'll need to run the project setup from the
root project directory:

```sh
make bootstrap
```

This command is handled by the `Makefile` file in the root project directory, as
are a few others.

_NOTE: You'll want to occasionally run `make bootstrap` to keep your project up-to-date, especially when there are dependency updates._

Now you can run the web server and background workers for asynchronous jobs:

```sh
make run-procfile
```

This will run all of the services within the same shell session.  If you need to
run them separately to help with debugging or tracing logs, you can do so by
opening three sepearate shell sessions and running one of these commands in each
one separately:

- `make run-celery` - Handles the asynchronous jobs
- `make run-celery-beat` - Handles the scheduling of asynchronous jobs
- `make run-flask` - Runs the web server

## Python Dependency Management

We're using [`Poetry`](https://python-poetry.org/) for managing our Python
dependencies and local virtual environments. When it comes to managing the
Python dependencies, there are a couple of things to bear in mind.

For situations where you manually manipulate the `pyproject.toml` file, you
should use the `make py-lock` command to sync the `poetry.lock` file. This will
ensure that you don't inadvertently bring in other transitive dependency updates
that have not been fully tested with the project yet.

If you're just trying to update a dependency to a newer (or the latest) version,
you should let Poetry take care of that for you by running the following:

```sh
poetry update <dependency> [<dependency>...]
```

You can specify more than one dependency together. With this command, Poetry
will do the following for you:

- Find the latest compatible version(s) of the specified dependency/dependencies
- Install the new versions
- Update and sync the `poetry.lock` file

In either situation, once you are finished and have verified the dependency
changes are working, please be sure to commit both the `pyproject.toml` and
`poetry.lock` files.

### Keeping the notification-utils Dependency Up-to-Date

The `notifications-utils` dependency references the other repository we have at
https://github.com/GSA/notifications-utils - this dependency requires a bit of
extra legwork to ensure it stays up-to-date.

Whenever a PR is merged in the `notifications-utils` repository, we need to make
sure the changes are pulled in here and committed to this repository as well.
You can do this by going through these steps:

- Make sure your local `main` branch is up-to-date
- Create a new branch to work in
- Run `make update-utils`
- Commit the updated `poetry.lock` file and push the changes
- Make a new PR with the change
- Have the PR get reviewed and merged

## Known Installation Issues

### Python Installation Errors

On M1 Macs, if you get a `fatal error: 'Python.h' file not found` message, try a
different method of installing Python. The recommended approach is to use
[`pyenv`](https://github.com/pyenv/pyenv), as noted above in the installation
instructions.

If you're using PyCharm for Python development, we've noticed some quirkiness
with the IDE and the interaction between Poetry and virtual environment
management that could cause a variety of problems to come up during project
setup and dependency management. Other tools, such as Visual Studio Code, have
proven to be a smoother experience for folks.

### PostgreSQL Installation Errors

A direct installation of PostgreSQL will not put the `createdb` command on your
`$PATH`. It can be added there in your shell startup script, or a
Homebrew-managed installation of PostgreSQL will take care of it. See the
instructions above for more details.

## Documentation

- [Infrastructure overview](./docs/all.md#infrastructure-overview)
  - [GitHub Repositories](./docs/all.md#github-repositories)
  - [Terraform](./docs/all.md#terraform)
  - [AWS](./docs/all.md#aws)
  - [New Relic](./docs/all.md#new-relic)
  - [Onboarding](./docs/all.md#onboarding)
  - [Setting up the infrastructure](./docs/all.md#setting-up-the-infrastructure)
- [Using the logs](./docs/all.md#using-the-logs)
- [Testing](./docs/all.md#testing)
  - [CI testing](./docs/all.md#ci-testing)
  - [Manual testing](./docs/all.md#manual-testing)
  - [To run a local OWASP scan](./docs/all.md#to-run-a-local-owasp-scan)
- [Deploying](./docs/all.md#deploying)
  - [Egress Proxy](./docs/all.md#egress-proxy)
  - [Managing environment variables](./docs/all.md#managing-environment-variables)
  - [Sandbox environment](./docs/all.md#sandbox-environment)
- [Database management](./docs/all.md#database-management)
  - [Initial state](./docs/all.md#initial-state)
  - [Data Model Diagram](./docs/all.md#data-model-diagram)
  - [Migrations](./docs/all.md#migrations)
  - [Purging user data](./docs/all.md#purging-user-data)
- [One-off tasks](./docs/all.md#one-off-tasks)
- [How messages are queued and sent](./docs/all.md#how-messages-are-queued-and-sent)
- [Writing public APIs](./docs/all.md#writing-public-apis)
  - [Overview](./docs/all.md#overview)
  - [Documenting APIs](./docs/all.md#documenting-apis)
  - [New APIs](./docs/all.md#new-apis)
- [API Usage](./docs/all.md#api-usage)
  - [Connecting to the API](./docs/all.md#connecting-to-the-api)
  - [Postman Documentation](./docs/all.md#postman-documentation)
  - [Using OpenAPI documentation](./docs/all.md#using-openapi-documentation)
- [Queues and tasks](./docs/all.md#queues-and-tasks)
  - [Priority queue](./docs/all.md#priority-queue)
  - [Celery scheduled tasks](./docs/all.md#celery-scheduled-tasks)
- [US Notify](./docs/all.md#us-notify)
  - [System Description](./docs/all.md#system-description)
- [Run Book](./docs/all.md#run-book)
  - [ Alerts, Notifications, Monitoring](./docs/all.md#-alerts-notifications-monitoring)
  - [ Restaging Apps](./docs/all.md#-restaging-apps)
  - [ Smoke-testing the App](./docs/all.md#-smoke-testing-the-app)
  - [ Configuration Management](./docs/all.md#-configuration-management)
  - [ DNS Changes](./docs/all.md#-dns-changes)
  - [Exporting test results for compliance monitoring](./docs/all.md#exporting-test-results-for-compliance-monitoring)
  - [ Known Gotchas](./docs/all.md#-known-gotchas)
  - [ User Account Management](./docs/all.md#-user-account-management)
  - [ SMS Phone Number Management](./docs/all.md#-sms-phone-number-management)
- [Data Storage Policies \& Procedures](./docs/all.md#data-storage-policies--procedures)
  - [Potential PII Locations](./docs/all.md#potential-pii-locations)
  - [Data Retention Policy](./docs/all.md#data-retention-policy)

## License && public domain

Work through [commit `e604385`](https://github.com/GSA/notifications-api/commit/e604385e0cf4c2ab8c6451b7120ceb196cce21b5) is licensed by the UK government under the MIT license. Work after that commit is in the worldwide public domain. See [LICENSE.md](./LICENSE.md) for more information.

## Contributing

As stated in [CONTRIBUTING.md](CONTRIBUTING.md), all contributions to this project will be released under the CC0 dedication. By submitting a pull request, you are agreeing to comply with this waiver of copyright interest.
