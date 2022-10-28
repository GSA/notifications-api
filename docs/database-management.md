# Database management

## Initial state

In Notify, several aspects of the system are loaded into the database via migration. This means that
application setup requires loading and overwriting historical data in order to arrive at the current
configuration.

[Here are notes](https://docs.google.com/document/d/1ZgiUtJFvRBKBxB1ehiry2Dup0Q5iIwbdCU5spuqUFTo/edit#)
about what is loaded into which tables, and some plans for how we might manage that in the future.

Flask does not seem to have a great way to squash migrations, but rather wants you to recreate them
from the DB structure. This means it's easy to recreate the tables, but hard to recreate the initial data.

## Data Model Diagram

A diagram of Notify's data model is available [in our compliance repo](https://github.com/GSA/us-notify-compliance/blob/main/diagrams/rendered/apps/data.logical.pdf).

## Migrations

Create a migration:

```
flask db migrate
```

Trim any auto-generated stuff down to what you want, and manually rename it to be in numerical order.
We should only have one migration branch.

Running migrations locally:

```
flask db upgrade
```

This should happen automatically on cloud.gov, but if you need to run a one-off migration for some reason:

```
cf run-task notifications-api-staging --commmand "flask db upgrade" --name db-upgrade
```

## Purging user data

There is a Flask command to wipe user-created data (users, services, etc.).

The command should stop itself if it's run in a production environment, but, you know, please don't run it
in a production environment.

Running locally: 

```
flask command purge_functional_test_data -u <functional tests user name prefix>
```

Running on cloud.gov:

```
cf run-task notify-api "flask command purge_functional_test_data -u <functional tests user name prefix>"
```
