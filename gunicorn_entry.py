from gevent import monkey

monkey.patch_all()

import newrelic.agent  # noqa

newrelic.agent.initialize("./newrelic.ini")

from application import application  # noqa
