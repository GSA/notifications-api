import os  # noqa
import socket  # noqa
import sys  # noqa
import traceback  # noqa

import gunicorn  # noqa

# This will give us a better stack trace if
workers = 4
worker_class = "gevent"
worker_connections = 256
bind = "0.0.0.0:{}".format(os.getenv("PORT"))
statsd_host = "{}:8125".format(os.getenv("STATSD_HOST"))
gunicorn.SERVER_SOFTWARE = "None"
timeout = 240


def on_starting(server):
    server.log.info("Starting Notifications API")


def worker_abort(worker):
    worker.log.info("worker received ABORT {}".format(worker.pid))
    for _threadId, stack in sys._current_frames().items():
        worker.log.error("".join(traceback.format_stack(stack)))


def on_exit(server):
    server.log.info("Stopping Notifications API")


def worker_int(worker):
    worker.log.info("worker: received SIGINT {}".format(worker.pid))
