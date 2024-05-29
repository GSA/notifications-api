from notifications_utils.take import Take


def _uppercase(value):
    return value.upper()


def _append(value, to_append):
    return value + to_append


def _prepend_with_service_name(value, service_name=None):
    return "{}: {}".format(service_name, value)


def test_take():
    assert "Service name: HELLO WORLD!" == Take("hello world").then(_uppercase).then(
        _append, "!"
    ).then(_prepend_with_service_name, service_name="Service name")
