from sqlalchemy import select, update

from app import db
from app.dao.dao_utils import autocommit
from app.models import ServiceDataRetention
from app.utils import utc_now


def fetch_service_data_retention_by_id(service_id, data_retention_id):
    stmt = select(ServiceDataRetention).where(
        ServiceDataRetention.service_id == service_id,
        ServiceDataRetention.id == data_retention_id,
    )
    return db.session.execute(stmt).scalars().first()


def fetch_service_data_retention(service_id):
    stmt = (
        select(ServiceDataRetention)
        .where(ServiceDataRetention.service_id == service_id)
        .order_by(
            # in the order that models.notification_types are created (email, sms, letter)
            ServiceDataRetention.notification_type
        )
    )
    return db.session.execute(stmt).scalars().all()


def fetch_service_data_retention_by_notification_type(service_id, notification_type):
    stmt = select(ServiceDataRetention).where(
        ServiceDataRetention.service_id == service_id,
        ServiceDataRetention.notification_type == notification_type,
    )
    return db.session.execute(stmt).scalars().first()


@autocommit
def insert_service_data_retention(service_id, notification_type, days_of_retention):
    new_data_retention = ServiceDataRetention(
        service_id=service_id,
        notification_type=notification_type,
        days_of_retention=days_of_retention,
    )

    db.session.add(new_data_retention)
    return new_data_retention


@autocommit
def update_service_data_retention(
    service_data_retention_id, service_id, days_of_retention
):
    stmt = (
        update(ServiceDataRetention)
        .where(
            ServiceDataRetention.id == service_data_retention_id,
            ServiceDataRetention.service_id == service_id,
        )
        .values({"days_of_retention": days_of_retention, "updated_at": utc_now()})
    )
    result = db.session.execute(stmt)
    return result.rowcount


def fetch_service_data_retention_for_all_services_by_notification_type(
    notification_type,
):
    stmt = select(ServiceDataRetention).where(
        ServiceDataRetention.notification_type == notification_type
    )
    return db.session.execute(stmt).scalars().all()
