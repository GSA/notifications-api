from sqlalchemy import select

from app import db
from app.dao.dao_utils import autocommit
from app.enums import UserState
from app.models import ServiceUser, User


def dao_get_service_user(user_id, service_id):
    stmt = select(ServiceUser).where(
        ServiceUser.user_id == user_id, ServiceUser.service_id == service_id
    )
    return db.session.execute(stmt).scalars().one_or_none()


def dao_get_active_service_users(service_id):

    stmt = (
        select(ServiceUser)
        .join(User, User.id == ServiceUser.user_id)
        .where(User.state == UserState.ACTIVE, ServiceUser.service_id == service_id)
    )
    return db.session.execute(stmt).scalars().all()


def dao_get_service_users_by_user_id(user_id):
    return (
        db.session.execute(select(ServiceUser).where(ServiceUser.user_id == user_id))
        .scalars()
        .all()
    )


@autocommit
def dao_update_service_user(service_user):
    db.session.add(service_user)
