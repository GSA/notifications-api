import json
import os
from contextlib import suppress
from urllib import parse

from cachetools import TTLCache, cached
from flask import current_app

from app import (
    create_uuid,
    db,
    notification_provider_clients,
    redis_store,
)
from app.aws.s3 import get_personalisation_from_s3, get_phone_number_from_s3
from app.celery.test_key_tasks import send_email_response, send_sms_response
from app.dao.email_branding_dao import dao_get_email_branding_by_id
from app.dao.notifications_dao import (
    dao_update_notification,
    update_notification_message_id,
)
from app.dao.provider_details_dao import get_provider_details_by_notification_type
from app.dao.service_sms_sender_dao import dao_get_sms_senders_by_service_id
from app.enums import BrandType, KeyType, NotificationStatus, NotificationType
from app.exceptions import NotificationTechnicalFailureException
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.utils import hilite, utc_now
from notifications_utils.clients.redis import total_limit_cache_key
from notifications_utils.template import (
    HTMLEmailTemplate,
    PlainTextEmailTemplate,
    SMSMessageTemplate,
)


def send_sms_to_provider(notification):
    """Final step in the message send flow.

    Get data for recipient, template,
    notification and send it to sns.
    """
    # Take this path for report generation, where we know
    # everything is in the cache.

    if "verify_code" not in str(notification.personalisation):
        personalisation = get_personalisation_from_s3(
            notification.service_id,
            notification.job_id,
            notification.job_row_number,
        )
        notification.personalisation = personalisation

    service = SerialisedService.from_id(notification.service_id)
    message_id = None
    if not service.active:
        technical_failure(notification=notification)
        return

    if notification.status == NotificationStatus.CREATED:
        # We get the provider here (which is only aws sns)
        provider = provider_to_use(NotificationType.SMS, notification.international)
        if not provider:
            technical_failure(notification=notification)
            return

        template_model = SerialisedTemplate.from_id_and_service_id(
            template_id=notification.template_id,
            service_id=service.id,
            version=notification.template_version,
        )

        template = SMSMessageTemplate(
            template_model.__dict__,
            values=notification.personalisation,
            prefix=service.name,
            show_prefix=service.prefix_sms,
        )
        if notification.key_type == KeyType.TEST:
            update_notification_to_sending(notification, provider)
            send_sms_response(provider.name, str(notification.id))

        else:
            try:
                # End DB session here so that we don't have a connection stuck open waiting on the call
                # to one of the SMS providers
                # We don't want to tie our DB connections being open to the performance of our SMS
                # providers as a slow down of our providers can cause us to run out of DB connections
                # Therefore we pull all the data from our DB models into `send_sms_kwargs`now before
                # closing the session (as otherwise it would be reopened immediately)

                # We start by trying to get the phone number from a job in s3.  If we fail, we assume
                # the phone number is for the verification code on login, which is not a job.
                recipient = None
                # It is our 2facode, maybe
                recipient = _get_verify_code(notification)
                if recipient is None:
                    recipient = get_phone_number_from_s3(
                        notification.service_id,
                        notification.job_id,
                        notification.job_row_number,
                    )

                # TODO current we allow US phone numbers to be uploaded without the country code (1)
                # This will break certain international phone numbers (Norway, Denmark, East Timor)
                # When we officially announce support for international numbers, US numbers must contain
                # their country code.
                recipient = str(recipient)
                if len(recipient) == 10:
                    if os.getenv("NOTIFY_ENVIRONMENT") not in [
                        "test"
                    ]:  # we want to test intl support
                        recipient = f"1{recipient}"

                sender_numbers = get_sender_numbers(notification)
                if notification.reply_to_text not in sender_numbers:
                    raise ValueError(
                        f"{notification.reply_to_text} not in {sender_numbers} #notify-debug-admin-1701"
                    )

                send_sms_kwargs = {
                    "to": recipient,
                    "content": str(template),
                    "reference": str(notification.id),
                    "sender": notification.reply_to_text,
                    "international": notification.international,
                }
                db.session.close()  # no commit needed as no changes to objects have been made above
                real_sender_number = notification.reply_to_text
                # interleave spaces to bypass PII scrubbing since sender number is not PII
                arr = list(real_sender_number)
                real_sender_number = " ".join(arr)
                message_id = provider.send_sms(**send_sms_kwargs)

                update_notification_message_id(notification.id, message_id)
            except Exception as e:
                n = notification
                msg = f"FAILED send to sms, job_id: {n.job_id} row_number {n.job_row_number} message_id {message_id}"
                current_app.logger.exception(hilite(msg))

                notification.billable_units = template.fragment_count
                dao_update_notification(notification)
                raise e
            else:
                # Here we map the job_id and row number to the aws message_id
                n = notification
                msg = f"Send to AWS!!! for job_id {n.job_id} row_number {n.job_row_number} message_id {message_id}"
                current_app.logger.info(hilite(msg))
                notification.billable_units = template.fragment_count
                update_notification_to_sending(notification, provider)

                cache_key = total_limit_cache_key(service.id)
                redis_store.incr(cache_key)

    return message_id


def _get_verify_code(notification):
    key = f"2facode-{notification.id}".replace(" ", "")
    recipient = redis_store.get(key)
    with suppress(AttributeError):
        recipient = recipient.decode("utf-8")
    return recipient


def get_sender_numbers(notification):
    possible_senders = dao_get_sms_senders_by_service_id(notification.service_id)
    sender_numbers = []
    for possible_sender in possible_senders:
        sender_numbers.append(possible_sender.sms_sender)
    return sender_numbers


def send_email_to_provider(notification):
    # Someone needs an email, possibly new registration
    recipient = redis_store.get(f"email-address-{notification.id}")
    recipient = recipient.decode("utf-8")
    personalisation = redis_store.get(f"email-personalisation-{notification.id}")
    if personalisation:
        p = personalisation.decode("utf-8")

        p = json.loads(p)
        notification.personalisation = p

    service = SerialisedService.from_id(notification.service_id)
    if not service.active:
        technical_failure(notification=notification)
        return
    if notification.status == NotificationStatus.CREATED:
        provider = provider_to_use(NotificationType.EMAIL, False)
        template_dict = SerialisedTemplate.from_id_and_service_id(
            template_id=notification.template_id,
            service_id=service.id,
            version=notification.template_version,
        ).__dict__

        html_email = HTMLEmailTemplate(
            template_dict,
            values=notification.personalisation,
            **get_html_email_options(service),
        )

        plain_text_email = PlainTextEmailTemplate(
            template_dict, values=notification.personalisation
        )

        html_email = str(html_email)
        html_email = html_email.replace("%5B", "")
        html_email = html_email.replace("%5D", "")
        html_email = html_email.replace("(", "")
        html_email = html_email.replace(")", "")

        if notification.key_type == KeyType.TEST:
            notification.reference = str(create_uuid())
            update_notification_to_sending(notification, provider)
            send_email_response(notification.reference, recipient)
        else:
            from_address = (
                f'"{service.name}" <{service.email_from}@'
                f'{current_app.config["NOTIFY_EMAIL_DOMAIN"]}>'
            )

            reference = provider.send_email(
                from_address,
                recipient,
                plain_text_email.subject,
                body=str(plain_text_email),
                html_body=html_email,
                reply_to_address=notification.reply_to_text,
            )
            notification.reference = reference
            update_notification_to_sending(notification, provider)


def update_notification_to_sending(notification, provider):
    notification.sent_at = utc_now()
    notification.sent_by = provider.name
    if notification.status not in NotificationStatus.completed_types():
        notification.status = NotificationStatus.SENDING

    dao_update_notification(notification)


provider_cache = TTLCache(maxsize=8, ttl=10)


@cached(cache=provider_cache)
def provider_to_use(notification_type, international=True):
    active_providers = [
        p
        for p in get_provider_details_by_notification_type(
            notification_type, international
        )
        if p.active
    ]

    if not active_providers:
        current_app.logger.error(f"{notification_type} failed as no active providers")
        raise Exception(f"No active {notification_type} providers")

    # we only have sns
    chosen_provider = active_providers[0]

    return notification_provider_clients.get_client_by_name_and_type(
        chosen_provider.identifier, notification_type
    )


def get_logo_url(base_url, logo_file):
    base_url = parse.urlparse(base_url)
    netloc = base_url.netloc

    if base_url.netloc.startswith("localhost"):
        netloc = "notify.tools"
    elif base_url.netloc.startswith("www"):
        # strip "www."
        netloc = base_url.netloc[4:]

    logo_url = parse.ParseResult(
        scheme=base_url.scheme,
        netloc="static-logos." + netloc,
        path=logo_file,
        params=base_url.params,
        query=base_url.query,
        fragment=base_url.fragment,
    )
    return parse.urlunparse(logo_url)


def get_html_email_options(service):
    if service.email_branding is None:
        return {
            "govuk_banner": True,
            "brand_banner": False,
        }
    if isinstance(service, SerialisedService):
        branding = dao_get_email_branding_by_id(service.email_branding)
    else:
        branding = service.email_branding

    logo_url = (
        get_logo_url(current_app.config["ADMIN_BASE_URL"], branding.logo)
        if branding.logo
        else None
    )

    return {
        "govuk_banner": branding.brand_type == BrandType.BOTH,
        "brand_banner": branding.brand_type == BrandType.ORG_BANNER,
        "brand_colour": branding.colour,
        "brand_logo": logo_url,
        "brand_text": branding.text,
        "brand_name": branding.name,
    }


def technical_failure(notification):
    notification.status = NotificationStatus.TECHNICAL_FAILURE
    dao_update_notification(notification)
    raise NotificationTechnicalFailureException(
        f"Send {notification.notification_type} for notification id {notification.id} "
        f"to provider is not allowed: service {notification.service_id} is inactive"
    )
