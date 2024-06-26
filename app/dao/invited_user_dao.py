from datetime import timedelta

from app import db
from app.enums import InvitedUserStatus
from app.models import InvitedUser
from app.utils import utc_now


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
        InvitedUser.status == InvitedUserStatus.EXPIRED,
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
            InvitedUser.created_at <= utc_now() - timedelta(days=2),
            InvitedUser.status.in_((InvitedUserStatus.PENDING,)),
        )
        .update({InvitedUser.status: InvitedUserStatus.EXPIRED})
    )
    db.session.commit()
    return expired
