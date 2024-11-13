from sqlalchemy import func, select

from app import db
from app.dao.events_dao import dao_create_event
from app.models import Event


def test_create_event(notify_db_session):
    stmt = select(func.count()).select_from(Event)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 0
    data = {
        "event_type": "sucessful_login",
        "data": {"something": "random", "in_fact": "could be anything"},
    }

    event = Event(**data)
    dao_create_event(event)

    stmt = select(func.count()).select_from(Event)
    count = db.session.execute(stmt).scalar() or 0
    assert count == 1
    event_from_db = Event.query.first()
    assert event == event_from_db
