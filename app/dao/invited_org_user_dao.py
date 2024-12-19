from datetime import timedelta

from sqlalchemy import select

from app import db
from app.models import InvitedOrganizationUser
from app.utils import utc_now


def save_invited_org_user(invited_org_user):
    db.session.add(invited_org_user)
    db.session.commit()


def get_invited_org_user(organization_id, invited_org_user_id):
    return (
        db.session.execute(
            select(InvitedOrganizationUser).where(
                InvitedOrganizationUser.organization_id == organization_id,
                InvitedOrganizationUser.id == invited_org_user_id,
            )
        )
        .scalars()
        .one()
    )


def get_invited_org_user_by_id(invited_org_user_id):
    return (
        db.session.execute(
            select(InvitedOrganizationUser).where(
                InvitedOrganizationUser.id == invited_org_user_id
            )
        )
        .scalars()
        .one()
    )


def get_invited_org_users_for_organization(organization_id):
    return (
        db.session.execute(
            select(InvitedOrganizationUser).where(
                InvitedOrganizationUser.organization_id == organization_id
            )
        )
        .scalars()
        .all()
    )


def delete_org_invitations_created_more_than_two_days_ago():
    deleted = (
        db.session.query(InvitedOrganizationUser)
        .filter(InvitedOrganizationUser.created_at <= utc_now() - timedelta(days=2))
        .delete()
    )
    db.session.commit()
    return deleted
