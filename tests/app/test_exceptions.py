from app.exceptions import DVLAException


def test_dvla_exception():
    dvla = DVLAException("a message")
    assert dvla.message == "a message"
