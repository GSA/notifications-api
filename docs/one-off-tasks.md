# One-off tasks

For these, we're using Flask commands, which live in [`/app/commands.py`](../app/commands.py).

This includes things that might be one-time operations! If we're running it on production, it should be a Flask 
command Using a command allows the operation to be tested, both with `pytest` and with trial runs in staging.

To see information about available commands, you can get a list with:

`pipenv run flask command`

Appending `--help` to any command will give you more information about parameters.

To run a command on cloud.gov, use this format:

`cf run-task CLOUD-GOV-APP --commmand "YOUR COMMAND HERE" --name YOUR-COMMAND`

[Here's more documentation](https://docs.cloudfoundry.org/devguide/using-tasks.html) about Cloud Foundry tasks.
