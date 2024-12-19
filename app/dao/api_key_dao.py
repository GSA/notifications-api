import uuid
from datetime import timedelta

from sqlalchemy import func, or_, select

from app import db
from app.dao.dao_utils import autocommit, version_class
from app.models import ApiKey
from app.utils import utc_now


@autocommit
@version_class(ApiKey)
def save_model_api_key(api_key):
    if not api_key.id:
        api_key.id = (
            uuid.uuid4()
        )  # must be set now so version history model can use same id
    api_key.secret = uuid.uuid4()
    db.session.add(api_key)


@autocommit
@version_class(ApiKey)
def expire_api_key(service_id, api_key_id):
    api_key = (
        db.session.execute(
            select(ApiKey).where(
                ApiKey.id == api_key_id, ApiKey.service_id == service_id
            )
        )
        # .scalars()
        .one()
    )
    api_key.expiry_date = utc_now()
    db.session.add(api_key)


def get_model_api_keys(service_id, id=None):
    if id:
        return (
            db.session.execute(
                select(ApiKey).where(
                    ApiKey.id == id,
                    ApiKey.service_id == service_id,
                    ApiKey.expiry_date == None, # noqa
                )
            )
            .scalars()
            .one()
        )
    seven_days_ago = utc_now() - timedelta(days=7)
    return (
        db.session.execute(
            select(ApiKey).where(
                or_(
                    ApiKey.expiry_date == None,  # noqa
                    func.date(ApiKey.expiry_date) > seven_days_ago,  # noqa
                ),
                ApiKey.service_id == service_id,
            )
        )
        .scalars()
        .all()
    )


def get_unsigned_secrets(service_id):
    """
    This method can only be exposed to the Authentication of the api calls.
    """
    api_keys = (
        db.session.execute(
            select(ApiKey).where(
                ApiKey.service_id == service_id, ApiKey.expiry_date == None  # noqa
            )
        )
        .scalars()
        .all()
    )
    keys = [x.secret for x in api_keys]
    return keys


def get_unsigned_secret(key_id):
    """
    This method can only be exposed to the Authentication of the api calls.
    """
    api_key = (
        db.session.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.expiry_date == None)  # noqa
        )
        .scalars()
        .one()
    )
    return api_key.secret
