# from gevent import monkey

# commenting out while we disable gevent
# monkey.patch_all()

import newrelic.agent  # noqa

newrelic.agent.initialize("./newrelic.ini")

from application import application  # noqa
