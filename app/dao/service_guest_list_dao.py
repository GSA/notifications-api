from sqlalchemy import delete, select

from app import db
from app.models import ServiceGuestList


def dao_fetch_service_guest_list(service_id):
    stmt = select(ServiceGuestList).where(ServiceGuestList.service_id == service_id)
    return db.session.execute(stmt).scalars().all()


def dao_add_and_commit_guest_list_contacts(objs):
    db.session.add_all(objs)
    db.session.commit()


def dao_remove_service_guest_list(service_id):
    stmt = delete(ServiceGuestList).where(ServiceGuestList.service_id == service_id)
    result = db.session.execute(stmt)
    db.session.commit()
    return result.rowcount
