# One-off tasks

For these, we're using Flask commands, which live in [`/app/commands.py`](../app/commands.py).

This includes things that might be one-time operations! Using a command allows the operation to be tested, 
both with `pytest` and with trial runs.

To run a command on cloud.gov, use this format:

```
cf run-task CLOUD-GOV-APP --commmand "YOUR COMMAND HERE" --name YOUR-COMMAND
```

[Here's more documentation](https://docs.cloudfoundry.org/devguide/using-tasks.html) about Cloud Foundry tasks.

## Celery scheduled tasks

After scheduling some tasks, run celery beat to get them moving:

```
make run-celery-beat
```
