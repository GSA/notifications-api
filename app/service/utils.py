import itertools

from notifications_utils.recipients import allowed_to_send_to

from app.dao.services_dao import dao_fetch_service_by_id
from app.enums import KeyType, RecipientType
from app.models import ServiceGuestList


def get_recipients_from_request(request_json, key, type):
    return [(type, recipient) for recipient in request_json.get(key)]


def get_guest_list_objects(service_id, request_json):
    return [
        ServiceGuestList.from_string(service_id, type, recipient)
        for type, recipient in (
            get_recipients_from_request(
                request_json, "phone_numbers", RecipientType.MOBILE
            )
            + get_recipients_from_request(
                request_json, "email_addresses", RecipientType.EMAIL
            )
        )
    ]


def service_allowed_to_send_to(
    recipient, service, key_type, allow_guest_list_recipients=True
):
    if key_type == KeyType.TEST:
        return True

    if key_type == KeyType.NORMAL and not service.restricted:
        return True

    # Revert back to the ORM model here so we can get some things which
    # aren’t in the serialised model
    service = dao_fetch_service_by_id(service.id)

    team_members = itertools.chain.from_iterable(
        [user.mobile_number, user.email_address] for user in service.users
    )
    guest_list_members = [
        member.recipient for member in service.guest_list if allow_guest_list_recipients
    ]

    if (key_type == KeyType.NORMAL and service.restricted) or (
        key_type == KeyType.TEAM
    ):
        return allowed_to_send_to(
            recipient, itertools.chain(team_members, guest_list_members)
        )
