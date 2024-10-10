from sqlalchemy import select

from app import db
from app.dao.dao_utils import autocommit
from app.models import ServiceUser, User


def dao_get_service_user(user_id, service_id):
    # TODO: This has been changed to account for the test case failure
    # that used this method but have any service user to return. Somehow, this
    # started to throw an error with one() method in sqlalchemy 2.0 unlike 1.4
    # return ServiceUser.query.filter_by(
    #     user_id=user_id, service_id=service_id
    # ).one_or_none()
    stmt = select(ServiceUser).filter_by(user_id=user_id, service_id=service_id)
    return db.session.execute(stmt).scalars().one_or_none()


def dao_get_active_service_users(service_id):
    # query = (
    #     db.session.query(ServiceUser)
    #     .join(User, User.id == ServiceUser.user_id)
    #     .filter(User.state == "active", ServiceUser.service_id == service_id)
    # )

    # return query.all()

    stmt = (
        select(ServiceUser)
        .join(User, User.id == ServiceUser.user_id)
        .filter(User.state == "active", ServiceUser.service_id == service_id)
    )
    return db.session.execute(stmt).scalars().all()


def dao_get_service_users_by_user_id(user_id):
    return ServiceUser.query.filter_by(user_id=user_id).all()


@autocommit
def dao_update_service_user(service_user):
    db.session.add(service_user)
