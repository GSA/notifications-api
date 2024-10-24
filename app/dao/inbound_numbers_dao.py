from sqlalchemy import and_, select, update

from app import db
from app.dao.dao_utils import autocommit
from app.models import InboundNumber


def dao_get_inbound_numbers():
    stmt = select(InboundNumber).order_by(InboundNumber.updated_at)
    return db.session.execute(stmt).scalars().all()


def dao_get_available_inbound_numbers():
    stmt = select(InboundNumber).filter(
        InboundNumber.active, InboundNumber.service_id.is_(None)
    )
    return db.session.execute(stmt).scalars().all()


def dao_get_inbound_number_for_service(service_id):
    stmt = select(InboundNumber).filter(InboundNumber.service_id == service_id)
    return db.session.execute(stmt).scalars().first()


def dao_get_inbound_number(inbound_number_id):
    stmt = select(InboundNumber).filter(InboundNumber.id == inbound_number_id)
    return db.session.execute(stmt).scalars().first()


@autocommit
def dao_set_inbound_number_to_service(service_id, inbound_number):
    inbound_number.service_id = service_id
    db.session.add(inbound_number)


@autocommit
def dao_set_inbound_number_active_flag(service_id, active):
    stmt = select(InboundNumber).filter(InboundNumber.service_id == service_id)
    inbound_number = db.session.execute(stmt).scalars().first()
    inbound_number.active = active

    db.session.add(inbound_number)


@autocommit
def dao_allocate_number_for_service(service_id, inbound_number_id):
    stmt = (
        update(InboundNumber)
        .where(
            and_(
                InboundNumber.id == inbound_number_id,  # noqa
                InboundNumber.active == True,  # noqa
                InboundNumber.service_id == None,  # noqa
            )
        )
        .values({"service_id": service_id})
    )
    result = db.session.execute(stmt)
    if result.rowcount == 0:
        raise Exception("Inbound number: {} is not available".format(inbound_number_id))
    return db.session.get(InboundNumber, inbound_number_id)
