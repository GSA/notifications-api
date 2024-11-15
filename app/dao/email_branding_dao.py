from sqlalchemy import select

from app import db
from app.dao.dao_utils import autocommit
from app.models import EmailBranding


def dao_get_email_branding_options():
    return db.session.execute(select(EmailBranding)).scalars().all()


def dao_get_email_branding_by_id(email_branding_id):
    return (
        db.session.execute(select(EmailBranding).filter_by(id=email_branding_id))
        .scalars()
        .one()
    )


def dao_get_email_branding_by_name(email_branding_name):
    return (
        db.session.execute(select(EmailBranding).filter_by(name=email_branding_name))
        .scalars()
        .first()
    )


@autocommit
def dao_create_email_branding(email_branding):
    db.session.add(email_branding)


@autocommit
def dao_update_email_branding(email_branding, **kwargs):
    for key, value in kwargs.items():
        setattr(email_branding, key, value or None)
    db.session.add(email_branding)
