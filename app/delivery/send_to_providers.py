from datetime import datetime
from urllib import parse

from cachetools import TTLCache, cached
from flask import current_app
from notifications_utils.template import (
    HTMLEmailTemplate,
    PlainTextEmailTemplate,
    SMSMessageTemplate,
)

from app import create_uuid, db, notification_provider_clients, redis_store
from app.aws.s3 import get_phone_number_from_s3
from app.celery.test_key_tasks import send_email_response, send_sms_response
from app.dao.email_branding_dao import dao_get_email_branding_by_id
from app.dao.notifications_dao import dao_update_notification
from app.dao.provider_details_dao import get_provider_details_by_notification_type
from app.enums import NotificationType
from app.exceptions import NotificationTechnicalFailureException
from app.models import (
    BRANDING_BOTH,
    BRANDING_ORG_BANNER,
    KEY_TYPE_TEST,
    NOTIFICATION_SENDING,
    NOTIFICATION_STATUS_TYPES_COMPLETED,
    NOTIFICATION_TECHNICAL_FAILURE,
)
from app.serialised_models import SerialisedService, SerialisedTemplate


def send_sms_to_provider(notification):
    service = SerialisedService.from_id(notification.service_id)
    message_id = None
    if not service.active:
        technical_failure(notification=notification)
        return

    if notification.status == "created":
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
        if notification.key_type == KEY_TYPE_TEST:
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
                try:
                    recipient = get_phone_number_from_s3(
                        notification.service_id,
                        notification.job_id,
                        notification.job_row_number,
                    )
                except Exception:
                    # It is our 2facode, maybe
                    key = f"2facode-{notification.id}".replace(" ", "")
                    recipient = redis_store.raw_get(key)

                    if recipient:
                        recipient = recipient.decode("utf-8")

                if recipient is None:
                    si = notification.service_id
                    ji = notification.job_id
                    jrn = notification.job_row_number
                    raise Exception(
                        f"The recipient for (Service ID: {si}; Job ID: {ji}; Job Row Number {jrn} was not found."
                    )
                send_sms_kwargs = {
                    "to": recipient,
                    "content": str(template),
                    "reference": str(notification.id),
                    "sender": notification.reply_to_text,
                    "international": notification.international,
                }
                db.session.close()  # no commit needed as no changes to objects have been made above
                current_app.logger.info("sending to sms")
                message_id = provider.send_sms(**send_sms_kwargs)
                current_app.logger.info(f"got message_id {message_id}")
            except Exception as e:
                current_app.logger.error(e)
                notification.billable_units = template.fragment_count
                dao_update_notification(notification)
                raise e
            else:
                notification.billable_units = template.fragment_count
                update_notification_to_sending(notification, provider)
    return message_id


def send_email_to_provider(notification):
    service = SerialisedService.from_id(notification.service_id)
    if not service.active:
        technical_failure(notification=notification)
        return
    if notification.status == "created":
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
        # Someone needs an email, possibly new registration
        recipient = redis_store.get(f"email-address-{notification.id}")
        recipient = recipient.decode("utf-8")
        if notification.key_type == KEY_TYPE_TEST:
            notification.reference = str(create_uuid())
            update_notification_to_sending(notification, provider)
            send_email_response(notification.reference, recipient)
        else:
            from_address = '"{}" <{}@{}>'.format(
                service.name,
                service.email_from,
                current_app.config["NOTIFY_EMAIL_DOMAIN"],
            )

            reference = provider.send_email(
                from_address,
                recipient,
                plain_text_email.subject,
                body=str(plain_text_email),
                html_body=str(html_email),
                reply_to_address=notification.reply_to_text,
            )
            notification.reference = reference
            update_notification_to_sending(notification, provider)


def update_notification_to_sending(notification, provider):
    notification.sent_at = datetime.utcnow()
    notification.sent_by = provider.name
    if notification.status not in NOTIFICATION_STATUS_TYPES_COMPLETED:
        notification.status = NOTIFICATION_SENDING

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
        current_app.logger.error(
            "{} failed as no active providers".format(notification_type)
        )
        raise Exception("No active {} providers".format(notification_type))

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
        "govuk_banner": branding.brand_type == BRANDING_BOTH,
        "brand_banner": branding.brand_type == BRANDING_ORG_BANNER,
        "brand_colour": branding.colour,
        "brand_logo": logo_url,
        "brand_text": branding.text,
        "brand_name": branding.name,
    }


def technical_failure(notification):
    notification.status = NOTIFICATION_TECHNICAL_FAILURE
    dao_update_notification(notification)
    raise NotificationTechnicalFailureException(
        "Send {} for notification id {} to provider is not allowed: service {} is inactive".format(
            notification.notification_type, notification.id, notification.service_id
        )
    )
