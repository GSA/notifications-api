from sqlalchemy import select

from app import create_uuid, db
from app.dao.dao_utils import autocommit, version_class
from app.models import ServiceInboundApi
from app.utils import utc_now


@autocommit
@version_class(ServiceInboundApi)
def save_service_inbound_api(service_inbound_api):
    service_inbound_api.id = create_uuid()
    service_inbound_api.created_at = utc_now()
    db.session.add(service_inbound_api)


@autocommit
@version_class(ServiceInboundApi)
def reset_service_inbound_api(
    service_inbound_api, updated_by_id, url=None, bearer_token=None
):
    if url:
        service_inbound_api.url = url
    if bearer_token:
        service_inbound_api.bearer_token = bearer_token
    service_inbound_api.updated_by_id = updated_by_id
    service_inbound_api.updated_at = utc_now()

    db.session.add(service_inbound_api)


def get_service_inbound_api(service_inbound_api_id, service_id):
    return (
        db.session.execute(
            select(ServiceInboundApi).where(
                ServiceInboundApi.id == service_inbound_api_id,
                ServiceInboundApi.service_id == service_id,
            )
        )
        .scalars()
        .first()
    )


def get_service_inbound_api_for_service(service_id):
    return (
        db.session.execute(
            select(ServiceInboundApi).where(ServiceInboundApi.service_id == service_id)
        )
        .scalars()
        .first()
    )


@autocommit
def delete_service_inbound_api(service_inbound_api):
    db.session.delete(service_inbound_api)
