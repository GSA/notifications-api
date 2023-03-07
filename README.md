# US Notify API

This project is the core of [Notify](https://notifications-admin.app.cloud.gov/). It's cloned from the brilliant work of the team at [GOV.UK Notify](https://github.com/alphagov/notifications-api), cheers!

This repo contains:

- A public-facing REST API for Notify, which teams can integrate with using [API clients built by UK](https://www.notifications.service.gov.uk/documentation)
- An internal-only REST API built using Flask to manage services, users, templates, etc., which the [admin UI](http://github.com/18F/notifications-admin) talks to)
- Asynchronous workers built using Celery to put things on queues and read them off to be processed, sent to providers, updated, etc.

Our other repositories are:

- [notifications-admin](https://github.com/GSA/notifications-admin)
- [notifications-utils](https://github.com/GSA/notifications-utils)
- [us-notify-compliance](https://github.com/GSA/us-notify-compliance/)
- [notify-python-demo](https://github.com/GSA/notify-python-demo)

## Documentation, here and elsewhere

### About Notify

- [Roadmap](https://notifications-admin.app.cloud.gov/features/roadmap)
- [Using the API](./docs/api-usage.md)

### Infrastructure

- [Overview, setup, and onboarding](./docs/infra-overview.md)
- [Database management](./docs/database-management.md)
- [Celery queues and tasks](./docs/queues-and-tasks.md)

### Common dev work

- [Local setup](#local-setup)
- [Testing](./docs/testing.md), both automated and manual
- [Deploying](./docs/deploying.md)
- [Running one-off tasks](./docs/one-off-tasks.md)

## UK docs that may still be helpful

- [Writing public APIs](docs/writing-public-apis.md)
- [Updating dependencies](https://github.com/alphagov/notifications-manuals/wiki/Dependencies)

## Local setup

### Direct installation

1. Set up Postgres && Redis on your machine

1. Install [pipenv](https://pipenv.pypa.io/en/latest/)

1. Create the .env file

    ```
    cp sample.env .env
    # follow the instructions in .env
    ```

1. Run the project setup

    `make bootstrap`

1. Run the web server and background worker

    `make run-procfile`

1. Or run them individually:

    * Run Flask (web server)

        `make run-flask`

    * Run Celery (background worker)

        `make run-celery`


### VS Code && Docker installation

If you're working in VS Code, you can also leverage Docker for a containerized dev environment

1. Create the .env file

    ```
    cp sample.env .env
    # follow the instructions in .env
    ```

1. Install the Remote-Containers plug-in in VS Code

1. With Docker running, create the network:

    `docker network create notify-network`

1. Using the command palette (shift+cmd+p) or green button thingy in the bottom left, search and select “Remote Containers: Open Folder in Container...” When prompted, choose **devcontainer-api** folder (note: this is a *subfolder* of notifications-api). This will start the container in a new window, replacing the current one.

1. Wait a few minutes while things happen 🍵

1. Open a VS Code terminal and run the Flask application:

    `make run-flask`

1. Open another VS Code terminal and run Celery:

    `make run-celery`

NOTE: when you change .env in the future, you'll need to rebuild the devcontainer for the change to take effect. VS Code _should_ detect the change and prompt you with a toast notification during a cached build. If not, you can find a manual rebuild in command pallette or just `docker rm` the notifications-api container.

## License && public domain

Work through [commit `e604385`](https://github.com/GSA/notifications-api/commit/e604385e0cf4c2ab8c6451b7120ceb196cce21b5) is licensed by the UK government under the MIT license. Work after that commit is in the worldwide public domain. See [LICENSE.md](./LICENSE.md) for more information.

## Contributing

As stated in [CONTRIBUTING.md](CONTRIBUTING.md), all contributions to this project will be released under the CC0 dedication. By submitting a pull request, you are agreeing to comply with this waiver of copyright interest.
