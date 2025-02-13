from sqlalchemy import select

from app import create_uuid, db
from app.dao.dao_utils import autocommit, version_class
from app.enums import CallbackType
from app.models import ServiceCallbackApi
from app.utils import utc_now


@autocommit
@version_class(ServiceCallbackApi)
def save_service_callback_api(service_callback_api):
    service_callback_api.id = create_uuid()
    service_callback_api.created_at = utc_now()
    db.session.add(service_callback_api)


@autocommit
@version_class(ServiceCallbackApi)
def reset_service_callback_api(
    service_callback_api, updated_by_id, url=None, bearer_token=None
):
    if url:
        service_callback_api.url = url
    if bearer_token:
        service_callback_api.bearer_token = bearer_token
    service_callback_api.updated_by_id = updated_by_id
    service_callback_api.updated_at = utc_now()

    db.session.add(service_callback_api)


def get_service_callback_api(service_callback_api_id, service_id):
    return (
        db.session.execute(
            select(ServiceCallbackApi).where(
                ServiceCallbackApi.id == service_callback_api_id,
                ServiceCallbackApi.service_id == service_id,
            )
        )
        .scalars()
        .first()
    )


def get_service_delivery_status_callback_api_for_service(service_id):
    return (
        db.session.execute(
            select(ServiceCallbackApi).where(
                ServiceCallbackApi.service_id == service_id,
                ServiceCallbackApi.callback_type == CallbackType.DELIVERY_STATUS,
            )
        )
        .scalars()
        .first()
    )


def get_service_complaint_callback_api_for_service(service_id):
    return (
        db.session.execute(
            select(ServiceCallbackApi).where(
                ServiceCallbackApi.service_id == service_id,
                ServiceCallbackApi.callback_type == CallbackType.COMPLAINT,
            )
        )
        .scalars()
        .first()
    )


@autocommit
def delete_service_callback_api(service_callback_api):
    db.session.delete(service_callback_api)
