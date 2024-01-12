from datetime import datetime, timedelta

from app import db
from app.enums import InvitedUserStatusType
from app.models import InvitedUser


def save_invited_user(invited_user):
    db.session.add(invited_user)
    db.session.commit()


def get_invited_user_by_service_and_id(service_id, invited_user_id):
    return InvitedUser.query.filter(
        InvitedUser.service_id == service_id,
        InvitedUser.id == invited_user_id,
    ).one()


def get_expired_invite_by_service_and_id(service_id, invited_user_id):
    return InvitedUser.query.filter(
        InvitedUser.service_id == service_id,
        InvitedUser.id == invited_user_id,
        InvitedUser.status == InvitedUserStatusType.EXPIRED,
    ).one()


def get_invited_user_by_id(invited_user_id):
    return InvitedUser.query.filter(InvitedUser.id == invited_user_id).one()


def get_expired_invited_users_for_service(service_id):
    return InvitedUser.query.filter(InvitedUser.service_id == service_id).all()


def get_invited_users_for_service(service_id):
    return InvitedUser.query.filter(InvitedUser.service_id == service_id).all()


def expire_invitations_created_more_than_two_days_ago():
    expired = (
        db.session.query(InvitedUser)
        .filter(
            InvitedUser.created_at <= datetime.utcnow() - timedelta(days=2),
            InvitedUser.status.in_((InvitedUserStatusType.PENDING,)),
        )
        .update({InvitedUser.status: InvitedUserStatusType.EXPIRED})
    )
    db.session.commit()
    return expired
