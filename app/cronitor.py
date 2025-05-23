from functools import wraps

import requests
from flask import current_app


def cronitor(task_name):
    def decorator(func):
        def ping_cronitor(command):
            if not current_app.config["CRONITOR_ENABLED"]:
                return

            # it's useful to have a log that a periodic task has started in case it
            # get stuck without generating any other logs - we know it got this far
            current_app.logger.info(f"Pinging Cronitor for Celery task {task_name}")

            task_slug = current_app.config["CRONITOR_KEYS"].get(task_name)
            if not task_slug:
                current_app.logger.error(
                    "Cronitor enabled but task_name {} not found in environment".format(
                        task_name
                    )
                )
                return

            if command not in {"run", "complete", "fail"}:
                raise ValueError(
                    "command {} not a valid cronitor command".format(command)
                )

            try:
                resp = requests.get(
                    "https://cronitor.link/{}/{}".format(task_slug, command),
                    # cronitor limits msg to 1000 characters
                    params={
                        "host": current_app.config["API_HOST_NAME"],
                    },
                    timeout=30,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                current_app.logger.warning(
                    "Cronitor API failed for task {} due to {}".format(
                        task_name, repr(e)
                    )
                )

        @wraps(func)
        def inner_decorator(*args, **kwargs):
            ping_cronitor("run")
            status = "fail"
            try:
                ret = func(*args, **kwargs)
                status = "complete"
                return ret
            finally:
                ping_cronitor(status)

        return inner_decorator

    return decorator
