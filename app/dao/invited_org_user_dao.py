from datetime import datetime, timedelta

from app import db
from app.models import InvitedOrganizationUser


def save_invited_org_user(invited_org_user):
    db.session.add(invited_org_user)
    db.session.commit()


def get_invited_org_user(organization_id, invited_org_user_id):
    return InvitedOrganizationUser.query.filter_by(
        organization_id=organization_id, id=invited_org_user_id
    ).one()


def get_invited_org_user_by_id(invited_org_user_id):
    return InvitedOrganizationUser.query.filter_by(id=invited_org_user_id).one()


def get_invited_org_users_for_organization(organization_id):
    return InvitedOrganizationUser.query.filter_by(
        organization_id=organization_id
    ).all()


def delete_org_invitations_created_more_than_two_days_ago():
    deleted = (
        db.session.query(InvitedOrganizationUser)
        .filter(
            InvitedOrganizationUser.created_at <= datetime.utcnow() - timedelta(days=2)
        )
        .delete()
    )
    db.session.commit()
    return deleted
