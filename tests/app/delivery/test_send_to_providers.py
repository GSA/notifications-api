import json
from collections import namedtuple
from unittest.mock import ANY, MagicMock

import pytest
from flask import current_app
from requests import HTTPError
from sqlalchemy import select

import app
from app import db, notification_provider_clients
from app.cloudfoundry_config import cloud_config
from app.dao import notifications_dao
from app.dao.provider_details_dao import get_provider_details_by_identifier
from app.delivery import send_to_providers
from app.delivery.send_to_providers import (
    get_html_email_options,
    get_logo_url,
)
from app.enums import BrandType, KeyType, NotificationStatus, NotificationType
from app.exceptions import NotificationTechnicalFailureException
from app.models import EmailBranding, Notification
from app.serialised_models import SerialisedService
from app.utils import utc_now
from tests.app.db import (
    create_email_branding,
    create_notification,
    create_reply_to_email,
    create_service,
    create_service_sms_sender,
    create_service_with_defined_sms_sender,
    create_template,
)


def setup_function(_function):
    # pytest will run this function before each test. It makes sure the
    # state of the cache is not shared between tests.
    send_to_providers.provider_cache.clear()


@pytest.mark.parametrize(
    "international_provider_priority",
    (
        # Since there’s only one international provider it should always
        # be used, no matter what its priority is set to
        0,
        50,
        100,
    ),
)
def test_provider_to_use_should_only_return_sns_for_international(
    mocker,
    notify_db_session,
    international_provider_priority,
):
    sns = get_provider_details_by_identifier("sns")
    sns.priority = international_provider_priority

    ret = send_to_providers.provider_to_use(NotificationType.SMS, international=True)

    assert ret.name == "sns"


def test_provider_to_use_raises_if_no_active_providers(
    mocker, restore_provider_details
):
    sns = get_provider_details_by_identifier("sns")
    sns.active = False

    # flake8 doesn't like raises with a generic exception
    try:
        send_to_providers.provider_to_use(NotificationType.SMS)
        assert 1 == 0
    except Exception:
        assert 1 == 1


def test_should_send_personalised_template_to_correct_sms_provider_and_persist(
    sample_sms_template_with_html, mocker
):

    mocker.patch("app.delivery.send_to_providers._get_verify_code", return_value=None)
    db_notification = create_notification(
        template=sample_sms_template_with_html,
        personalisation={},
        status=NotificationStatus.CREATED,
        reply_to_text=sample_sms_template_with_html.service.get_default_sms_sender(),
    )

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_s3.return_value = "2028675309"

    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")
    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"name": "Jo"}

    send_to_providers.send_sms_to_provider(db_notification)

    mock_sns.send_sms.assert_called_once_with(
        to="2028675309",
        content="Sample service: Hello Jo\nHere is <em>some HTML</em> & entities",
        reference=str(db_notification.id),
        sender=current_app.config["FROM_NUMBER"],
        international=False,
    )

    notification = (
        db.session.execute(
            select(Notification).where(Notification.id == db_notification.id)
        )
        .scalars()
        .one()
    )

    assert notification.status == NotificationStatus.SENDING
    assert notification.sent_at <= utc_now()
    assert notification.sent_by == "sns"
    assert notification.billable_units == 1
    assert notification.personalisation == {"name": "Jo"}


def test_should_send_personalised_template_to_correct_email_provider_and_persist(
    sample_email_template_with_html, mocker
):

    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    utf8_encoded_email = "jo.smith@example.com".encode("utf-8")
    mock_redis.get.return_value = utf8_encoded_email
    email = utf8_encoded_email
    personalisation = {
        "name": "Jo",
    }
    personalisation = json.dumps(personalisation)
    personalisation = personalisation.encode("utf-8")
    mock_redis.get.side_effect = [email, personalisation]
    db_notification = create_notification(
        template=sample_email_template_with_html,
    )
    db_notification.personalisation = {"name": "Jo"}

    mock_boto_client = mocker.patch("boto3.client")
    mock_ses = MagicMock()
    mock_boto_client.return_value = mock_ses
    mock_ses.send_email.return_value = "reference"
    mock_ses.name = "ses"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_ses,
    )

    send_to_providers.send_email_to_provider(db_notification)
    mock_ses.send_email.assert_called_once_with(
        f'"Sample service" <sample.service@{cloud_config.ses_email_domain}>',
        "jo.smith@example.com",
        "Jo <em>some HTML</em>",
        body="Hello Jo\nThis is an email from GOV.\u200bUK with <em>some HTML</em>\n",
        html_body=ANY,
        reply_to_address=None,
    )

    assert "<!DOCTYPE html" in mock_ses.send_email.call_args[1]["html_body"]
    assert (
        "&lt;em&gt;some HTML&lt;/em&gt;"
        in mock_ses.send_email.call_args[1]["html_body"]
    )

    notification = (
        db.session.execute(
            select(Notification).where(Notification.id == db_notification.id)
        )
        .scalars()
        .one()
    )
    assert notification.status == NotificationStatus.SENDING
    assert notification.sent_at <= utc_now()
    assert notification.sent_by == "ses"
    assert notification.personalisation == {"name": "Jo"}


def test_should_not_send_email_message_when_service_is_inactive_notifcation_is_in_tech_failure(
    sample_service, sample_notification, mocker
):
    sample_service.active = False

    mock_client = MagicMock()
    mock_client.send_email.return_value = "reference"
    mocker.patch("app.aws_ses_client", mock_client)

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_s3.return_value = "2028675309"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"name": "Jo"}

    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    mock_redis.get.return_value = "jo.smith@example.com".encode("utf-8")
    email = "jo.smith@example.com".encode("utf-8")
    personalisation = {
        "name": "Jo",
    }

    personalisation = json.dumps(personalisation)
    personalisation = personalisation.encode("utf-8")
    mock_redis.get.side_effect = [email, personalisation]

    with pytest.raises(NotificationTechnicalFailureException) as e:
        send_to_providers.send_email_to_provider(sample_notification)
    assert str(sample_notification.id) in str(e.value)
    mock_client.send_email.assert_not_called()
    assert (
        db.session.get(Notification, sample_notification.id).status
        == NotificationStatus.TECHNICAL_FAILURE
    )


def test_should_not_send_sms_message_when_service_is_inactive_notification_is_in_tech_failure(
    sample_service, sample_notification, mocker
):
    sample_service.active = False

    mock_client = MagicMock()
    mock_client.send_sms.return_value = "reference"
    send_mock = mocker.patch("app.aws_sns_client", mock_client)

    mock_phone = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_phone.return_value = "15555555555"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    with pytest.raises(NotificationTechnicalFailureException) as e:
        send_to_providers.send_sms_to_provider(sample_notification)
    assert str(sample_notification.id) in str(e.value)
    send_mock.send_sms.assert_not_called()
    assert (
        db.session.get(Notification, sample_notification.id).status
        == NotificationStatus.TECHNICAL_FAILURE
    )


def test_send_sms_should_use_template_version_from_notification_not_latest(
    sample_template, mocker
):

    mocker.patch("app.delivery.send_to_providers._get_verify_code", return_value=None)
    db_notification = create_notification(
        template=sample_template,
        to_field="2028675309",
        status=NotificationStatus.CREATED,
        reply_to_text=sample_template.service.get_default_sms_sender(),
        normalised_to="2028675309",
    )

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_s3.return_value = "2028675309"

    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")
    mock_s3_p = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_s3_p.return_value = {"ignore": "ignore"}

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )

    version_on_notification = sample_template.version
    expected_template_id = sample_template.id

    # Change the template
    from app.dao.templates_dao import dao_get_template_by_id, dao_update_template

    sample_template.content = (
        sample_template.content + " another version of the template"
    )
    dao_update_template(sample_template)
    t = dao_get_template_by_id(sample_template.id)
    assert t.version > version_on_notification

    send_to_providers.send_sms_to_provider(db_notification)

    mock_sns.send_sms.assert_called_once_with(
        to="2028675309",
        content="Sample service: This is a template:\nwith a newline",
        reference=str(db_notification.id),
        sender=current_app.config["FROM_NUMBER"],
        international=False,
    )

    t = dao_get_template_by_id(expected_template_id)

    persisted_notification = notifications_dao.get_notification_by_id(
        db_notification.id
    )
    assert persisted_notification.to == db_notification.to
    assert persisted_notification.template_id == expected_template_id
    assert persisted_notification.template_version == version_on_notification
    assert persisted_notification.template_version != t.version
    assert persisted_notification.status == NotificationStatus.SENDING


def test_should_have_sending_status_if_fake_callback_function_fails(
    sample_notification, mocker
):
    mocker.patch(
        "app.delivery.send_to_providers.send_sms_response",
        side_effect=HTTPError,
    )

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_s3.return_value = "2028675309"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    sample_notification.key_type = KeyType.TEST
    with pytest.raises(HTTPError):
        send_to_providers.send_sms_to_provider(sample_notification)
    assert sample_notification.status == NotificationStatus.SENDING
    assert sample_notification.sent_by == "sns"


def test_should_not_send_to_provider_when_status_is_not_created(
    sample_template, mocker
):
    notification = create_notification(
        template=sample_template,
        status=NotificationStatus.SENDING,
    )

    mock_client = MagicMock()
    mock_client.send_sms.return_value = "reference"
    send_mock = mocker.patch("app.aws_sns_client", mock_client)
    response_mock = mocker.patch("app.delivery.send_to_providers.send_sms_response")

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_s3.return_value = "2028675309"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    send_to_providers.send_sms_to_provider(notification)

    send_mock.send_sms.assert_not_called()
    response_mock.assert_not_called()


def test_should_send_sms_with_downgraded_content(notify_db_session, mocker):
    # é, o, and u are in GSM.
    # ī, grapes, tabs, zero width space and ellipsis are not
    # ó isn't in GSM, but it is in the welsh alphabet so will still be sent

    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")
    mocker.patch("app.delivery.send_to_providers.redis_store", return_value=None)
    mocker.patch(
        "app.delivery.send_to_providers.get_sender_numbers", return_value=["testing"]
    )
    msg = "a é ī o u 🍇 foo\tbar\u200bbaz((misc))…"
    placeholder = "∆∆∆abc"
    gsm_message = "?ódz Housing Service: a é i o u ? foo barbaz???abc..."
    service = create_service(service_name="Łódź Housing Service")
    template = create_template(service, content=msg)
    db_notification = create_notification(
        template=template,
    )
    db_notification.personalisation = {"misc": placeholder}
    db_notification.reply_to_text = "testing"

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )

    mock_phone = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_phone.return_value = "15555555555"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"misc": placeholder}

    send_to_providers.send_sms_to_provider(db_notification)

    mock_sns.send_sms.assert_called_once_with(
        to=ANY, content=gsm_message, reference=ANY, sender=ANY, international=False
    )


def test_send_sms_should_use_service_sms_sender(
    sample_service, sample_template, mocker
):

    mocker.patch("app.delivery.send_to_providers.redis_store", return_value=None)

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )
    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")

    sms_sender = create_service_sms_sender(
        service=sample_service, sms_sender="123456", is_default=False
    )
    db_notification = create_notification(
        template=sample_template, reply_to_text=sms_sender.sms_sender
    )
    expected_sender_name = sms_sender.sms_sender
    mock_phone = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_phone.return_value = "15555555555"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    send_to_providers.send_sms_to_provider(
        db_notification,
    )

    mock_sns.send_sms.assert_called_once_with(
        to=ANY,
        content=ANY,
        reference=ANY,
        sender=expected_sender_name,
        international=False,
    )


def test_send_email_to_provider_should_not_send_to_provider_when_status_is_not_created(
    sample_email_template, mocker
):
    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    mock_redis.get.return_value = "test@example.com".encode("utf-8")

    notification = create_notification(
        template=sample_email_template, status=NotificationStatus.SENDING
    )

    mock_client = MagicMock()
    mock_client.send_email.return_value = "reference"
    mocker.patch("app.aws_ses_client", mock_client)
    mocker.patch("app.delivery.send_to_providers.send_email_response")

    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")
    mock_phone = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_phone.return_value = "15555555555"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}
    send_to_providers.send_sms_to_provider(notification)
    app.aws_ses_client.send_email.assert_not_called()
    app.delivery.send_to_providers.send_email_response.assert_not_called()


def test_send_email_should_use_service_reply_to_email(
    sample_service, sample_email_template, mocker
):
    mock_boto_client = mocker.patch("boto3.client")
    mock_ses = MagicMock()
    mock_boto_client.return_value = mock_ses
    mock_ses.send_email.return_value = "reference"
    mock_ses.name = "ses"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_ses,
    )

    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    mock_redis.get.return_value = "test@example.com".encode("utf-8")

    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    email = "foo@bar.com".encode("utf-8")
    personalisation = {}

    personalisation = json.dumps(personalisation)
    personalisation = personalisation.encode("utf-8")
    mock_redis.get.side_effect = [email, personalisation]

    db_notification = create_notification(
        template=sample_email_template, reply_to_text="foo@bar.com"
    )
    create_reply_to_email(service=sample_service, email_address="foo@bar.com")

    send_to_providers.send_email_to_provider(db_notification)

    mock_ses.send_email.assert_called_once_with(
        ANY,
        ANY,
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address="foo@bar.com",
    )


def test_get_html_email_renderer_should_return_for_normal_service(sample_service):
    options = send_to_providers.get_html_email_options(sample_service)
    assert options["govuk_banner"] is True
    assert "brand_colour" not in options.keys()
    assert "brand_logo" not in options.keys()
    assert "brand_text" not in options.keys()
    assert "brand_name" not in options.keys()


@pytest.mark.parametrize(
    "branding_type, govuk_banner",
    [(BrandType.ORG, False), (BrandType.BOTH, True), (BrandType.ORG_BANNER, False)],
)
def test_get_html_email_renderer_with_branding_details(
    branding_type, govuk_banner, notify_db_session, sample_service
):
    email_branding = EmailBranding(
        brand_type=branding_type,
        colour="#000000",
        logo="justice-league.png",
        name="Justice League",
        text="League of Justice",
    )
    sample_service.email_branding = email_branding
    notify_db_session.add_all([sample_service, email_branding])
    notify_db_session.commit()

    options = send_to_providers.get_html_email_options(sample_service)

    assert options["govuk_banner"] == govuk_banner
    assert options["brand_colour"] == "#000000"
    assert options["brand_text"] == "League of Justice"
    assert options["brand_name"] == "Justice League"

    if branding_type == BrandType.ORG_BANNER:
        assert options["brand_banner"] is True
    else:
        assert options["brand_banner"] is False


def test_get_html_email_renderer_with_branding_details_and_render_govuk_banner_only(
    notify_db_session, sample_service
):
    sample_service.email_branding = None
    notify_db_session.add_all([sample_service])
    notify_db_session.commit()

    options = send_to_providers.get_html_email_options(sample_service)

    assert options == {"govuk_banner": True, "brand_banner": False}


def test_get_html_email_renderer_prepends_logo_path(notify_api):
    Service = namedtuple("Service", ["email_branding"])
    EmailBranding = namedtuple(
        "EmailBranding",
        ["brand_type", "colour", "name", "logo", "text"],
    )

    email_branding = EmailBranding(
        brand_type=BrandType.ORG,
        colour="#000000",
        logo="justice-league.png",
        name="Justice League",
        text="League of Justice",
    )
    service = Service(
        email_branding=email_branding,
    )

    renderer = send_to_providers.get_html_email_options(service)

    assert (
        renderer["brand_logo"] == "http://static-logos.notify.tools/justice-league.png"
    )


def test_get_html_email_renderer_handles_email_branding_without_logo(notify_api):
    Service = namedtuple("Service", ["email_branding"])
    EmailBranding = namedtuple(
        "EmailBranding",
        ["brand_type", "colour", "name", "logo", "text"],
    )

    email_branding = EmailBranding(
        brand_type=BrandType.ORG_BANNER,
        colour="#000000",
        logo=None,
        name="Justice League",
        text="League of Justice",
    )
    service = Service(
        email_branding=email_branding,
    )

    renderer = send_to_providers.get_html_email_options(service)

    assert renderer["govuk_banner"] is False
    assert renderer["brand_banner"] is True
    assert renderer["brand_logo"] is None
    assert renderer["brand_text"] == "League of Justice"
    assert renderer["brand_colour"] == "#000000"
    assert renderer["brand_name"] == "Justice League"


@pytest.mark.parametrize(
    "base_url, expected_url",
    [
        # don't change localhost to prevent errors when testing locally
        ("http://localhost:6012", "http://static-logos.notify.tools/filename.png"),
        (
            "https://www.notifications.service.gov.uk",
            "https://static-logos.notifications.service.gov.uk/filename.png",
        ),
        ("https://notify.works", "https://static-logos.notify.works/filename.png"),
        (
            "https://staging-notify.works",
            "https://static-logos.staging-notify.works/filename.png",
        ),
        ("https://www.notify.works", "https://static-logos.notify.works/filename.png"),
        (
            "https://www.staging-notify.works",
            "https://static-logos.staging-notify.works/filename.png",
        ),
    ],
)
def test_get_logo_url_works_for_different_environments(base_url, expected_url):
    logo_file = "filename.png"

    logo_url = send_to_providers.get_logo_url(base_url, logo_file)

    assert logo_url == expected_url


@pytest.mark.parametrize(
    "starting_status, expected_status",
    [
        (NotificationStatus.DELIVERED, NotificationStatus.DELIVERED),
        (NotificationStatus.CREATED, NotificationStatus.SENDING),
        (NotificationStatus.TECHNICAL_FAILURE, NotificationStatus.TECHNICAL_FAILURE),
    ],
)
def test_update_notification_to_sending_does_not_update_status_from_a_final_status(
    sample_service, notify_db_session, starting_status, expected_status
):
    template = create_template(sample_service)
    notification = create_notification(template=template, status=starting_status)
    send_to_providers.update_notification_to_sending(
        notification,
        notification_provider_clients.get_client_by_name_and_type(
            "sns", NotificationType.SMS
        ),
    )
    assert notification.status == expected_status


def __update_notification(notification_to_update, research_mode, expected_status):
    if research_mode or notification_to_update.key_type == KeyType.TEST:
        notification_to_update.status = expected_status


@pytest.mark.parametrize(
    "research_mode,key_type, billable_units, expected_status",
    [
        (True, KeyType.NORMAL, 0, NotificationStatus.DELIVERED),
        (False, KeyType.NORMAL, 1, NotificationStatus.SENDING),
        (False, KeyType.TEST, 0, NotificationStatus.SENDING),
        (True, KeyType.TEST, 0, NotificationStatus.SENDING),
        (True, KeyType.TEAM, 0, NotificationStatus.DELIVERED),
        (False, KeyType.TEAM, 1, NotificationStatus.SENDING),
    ],
)
def test_should_update_billable_units_and_status_according_to_research_mode_and_key_type(
    sample_template, mocker, research_mode, key_type, billable_units, expected_status
):

    mocker.patch("app.delivery.send_to_providers.redis_store", return_value=None)
    mocker.patch(
        "app.delivery.send_to_providers.update_notification_message_id",
        return_value=None,
    )
    mocker.patch(
        "app.delivery.send_to_providers.get_sender_numbers", return_value=["testing"]
    )
    notification = create_notification(
        template=sample_template,
        billable_units=0,
        status=NotificationStatus.CREATED,
        key_type=key_type,
        reply_to_text="testing",
    )

    mocker.patch(
        "app.delivery.send_to_providers.update_notification_message_id",
        return_value=None,
    )

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )
    mocker.patch(
        "app.delivery.send_to_providers.send_sms_response",
        side_effect=__update_notification(notification, research_mode, expected_status),
    )

    if research_mode:
        sample_template.service.research_mode = True

    mock_phone = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")

    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")
    mock_phone.return_value = "15555555555"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    # So we don't treat it as a one off and have to mock other things
    mock_personalisation.return_value = {"ignore": "ignore"}

    send_to_providers.send_sms_to_provider(notification)
    assert notification.billable_units == billable_units
    assert notification.status == expected_status


def test_should_set_notification_billable_units_and_reduces_provider_priority_if_sending_to_provider_fails(
    sample_notification,
    mocker,
):

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )
    sample_notification.billable_units = 0
    assert sample_notification.sent_by is None

    mock_phone = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")

    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")
    mock_phone.return_value = "15555555555"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    # flake8 no longer likes raises with a generic exception
    try:
        send_to_providers.send_sms_to_provider(sample_notification)
        assert 1 == 0
    except Exception:
        assert 1 == 1

    assert sample_notification.billable_units == 1


def test_should_send_sms_to_international_providers(
    sample_template, sample_user, mocker
):

    mocker.patch("app.delivery.send_to_providers._get_verify_code", return_value=None)

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )
    notification_international = create_notification(
        template=sample_template,
        to_field="+6011-17224412",
        personalisation={"name": "Jo"},
        status=NotificationStatus.CREATED,
        international=True,
        reply_to_text=sample_template.service.get_default_sms_sender(),
        normalised_to="601117224412",
    )

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")

    mocker.patch("app.delivery.send_to_providers.update_notification_message_id")
    mock_s3.return_value = "601117224412"

    mocker.patch(
        "app.delivery.send_to_providers.update_notification_message_id",
        return_value=None,
    )
    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    send_to_providers.send_sms_to_provider(notification_international)

    mock_sns.send_sms.assert_called_once_with(
        to="601117224412",
        content=ANY,
        reference=str(notification_international.id),
        sender=current_app.config["FROM_NUMBER"],
        international=True,
    )

    assert notification_international.status == NotificationStatus.SENDING
    assert notification_international.sent_by == "sns"


@pytest.mark.parametrize(
    "sms_sender, expected_sender, prefix_sms, expected_content",
    [
        ("foo", "foo", False, "bar"),
        ("foo", "foo", True, "Sample service: bar"),
        # if 40604 is actually in DB then treat that as if entered manually
        ("40604", "40604", False, "bar"),
        # 'testing' is the FROM_NUMBER during unit tests
        ("testing", "testing", True, "Sample service: bar"),
        ("testing", "testing", False, "bar"),
    ],
)
def test_should_handle_sms_sender_and_prefix_message(
    mocker, sms_sender, prefix_sms, expected_sender, expected_content, notify_db_session
):

    mocker.patch("app.delivery.send_to_providers.redis_store", return_value=None)

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )

    mocker.patch(
        "app.delivery.send_to_providers.update_notification_message_id",
        return_value=None,
    )
    service = create_service_with_defined_sms_sender(
        sms_sender_value=sms_sender, prefix_sms=prefix_sms
    )
    template = create_template(service, content="bar")
    notification = create_notification(template, reply_to_text=sms_sender)

    mock_phone = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_phone.return_value = "15555555555"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    send_to_providers.send_sms_to_provider(notification)

    mock_sns.send_sms.assert_called_once_with(
        content=expected_content,
        sender=expected_sender,
        to=ANY,
        reference=ANY,
        international=False,
    )


def test_send_email_to_provider_uses_reply_to_from_notification(
    sample_email_template, mocker
):
    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    mock_redis.get.side_effect = [
        "test@example.com".encode("utf-8"),
        json.dumps({}).encode("utf-8"),
    ]
    mock_boto_client = mocker.patch("boto3.client")
    mock_ses = MagicMock()
    mock_boto_client.return_value = mock_ses
    mock_ses.send_email.return_value = "reference"
    mock_ses.name = "ses"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_ses,
    )

    db_notification = create_notification(
        template=sample_email_template,
        reply_to_text="test@test.com",
    )

    send_to_providers.send_email_to_provider(db_notification)

    mock_ses.send_email.assert_called_once_with(
        ANY,
        ANY,
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address="test@test.com",
    )


def test_send_sms_to_provider_should_use_normalised_to(mocker, client, sample_template):

    mocker.patch("app.delivery.send_to_providers._get_verify_code", return_value=None)
    mocker.patch(
        "app.delivery.send_to_providers.get_sender_numbers", return_value=["testing"]
    )

    mocker.patch(
        "app.delivery.send_to_providers.update_notification_message_id",
        return_value=None,
    )

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )
    notification = create_notification(
        template=sample_template,
        to_field="+12028675309",
        normalised_to="2028675309",
        reply_to_text="testing",
    )

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_s3.return_value = "12028675309"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}
    send_to_providers.send_sms_to_provider(notification)
    mock_sns.send_sms.assert_called_once_with(
        to="12028675309",
        content=ANY,
        reference=str(notification.id),
        sender=notification.reply_to_text,
        international=False,
    )


def test_send_email_to_provider_should_use_normalised_to(
    mocker, client, sample_email_template
):
    mock_boto_client = mocker.patch("boto3.client")
    mock_ses = MagicMock()
    mock_boto_client.return_value = mock_ses
    mock_ses.send_email.return_value = "reference"
    mock_ses.name = "ses"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_ses,
    )
    notification = create_notification(
        template=sample_email_template,
    )
    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    mock_redis.get.return_value = "test@example.com".encode("utf-8")

    mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    mock_redis.get.return_value = "jo.smith@example.com".encode("utf-8")
    email = "test@example.com".encode("utf-8")
    personalisation = {}

    personalisation = json.dumps(personalisation)
    personalisation = personalisation.encode("utf-8")
    mock_redis.get.side_effect = [email, personalisation]

    send_to_providers.send_email_to_provider(notification)
    mock_ses.send_email.assert_called_once_with(
        ANY,
        "test@example.com",
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address=notification.reply_to_text,
    )


def test_send_sms_to_provider_should_return_template_if_found_in_redis(
    mocker, client, sample_template
):

    mocker.patch("app.delivery.send_to_providers._get_verify_code", return_value=None)
    mocker.patch(
        "app.delivery.send_to_providers.get_sender_numbers", return_value=["testing"]
    )

    mocker.patch(
        "app.delivery.send_to_providers.update_notification_message_id",
        return_value=None,
    )
    from app.schemas import service_schema, template_schema

    service_dict = service_schema.dump(sample_template.service)
    template_dict = template_schema.dump(sample_template)

    mocker.patch(
        "app.redis_store.get",
        side_effect=[
            json.dumps({"data": service_dict}).encode("utf-8"),
            json.dumps({"data": template_dict}).encode("utf-8"),
        ],
    )
    mock_get_template = mocker.patch(
        "app.dao.templates_dao.dao_get_template_by_id_and_service_id"
    )
    mock_get_service = mocker.patch("app.dao.services_dao.dao_fetch_service_by_id")

    mock_boto_client = mocker.patch("boto3.client")
    mock_sns = MagicMock()
    mock_boto_client.return_value = mock_sns
    mock_sns.send_sms.return_value = "reference"
    mock_sns.name = "sns"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_sns,
    )
    notification = create_notification(
        template=sample_template,
        to_field="+447700900855",
        normalised_to="447700900855",
        reply_to_text="testing",
    )

    mock_s3 = mocker.patch("app.delivery.send_to_providers.get_phone_number_from_s3")
    mock_s3.return_value = "447700900855"

    mock_personalisation = mocker.patch(
        "app.delivery.send_to_providers.get_personalisation_from_s3"
    )
    mock_personalisation.return_value = {"ignore": "ignore"}

    send_to_providers.send_sms_to_provider(notification)
    assert mock_get_template.called is False
    assert mock_get_service.called is False
    mock_sns.send_sms.assert_called_once_with(
        to="447700900855",
        content=ANY,
        reference=str(notification.id),
        sender=notification.reply_to_text,
        international=False,
    )


def test_send_email_to_provider_should_return_template_if_found_in_redis(
    mocker, client, sample_email_template
):
    from app.schemas import service_schema, template_schema

    # mock_redis = mocker.patch("app.delivery.send_to_providers.redis_store")
    # mock_redis.get.return_value = "jo.smith@example.com".encode("utf-8")
    email = "test@example.com".encode("utf-8")
    personalisation = {
        "name": "Jo",
    }

    personalisation = json.dumps(personalisation)
    personalisation = personalisation.encode("utf-8")
    # mock_redis.get.side_effect = [email, personalisation]

    service_dict = service_schema.dump(sample_email_template.service)
    template_dict = template_schema.dump(sample_email_template)

    mocker.patch(
        "app.redis_store.get",
        side_effect=[
            email,
            personalisation,
            json.dumps({"data": service_dict}).encode("utf-8"),
            json.dumps({"data": template_dict}).encode("utf-8"),
        ],
    )
    mock_get_template = mocker.patch(
        "app.dao.templates_dao.dao_get_template_by_id_and_service_id"
    )
    mock_get_service = mocker.patch("app.dao.services_dao.dao_fetch_service_by_id")

    mock_boto_client = mocker.patch("boto3.client")
    mock_ses = MagicMock()
    mock_boto_client.return_value = mock_ses
    mock_ses.send_email.return_value = "reference"
    mock_ses.name = "ses"
    mocker.patch(
        "app.delivery.send_to_providers.provider_to_use",
        return_value=mock_ses,
    )

    notification = create_notification(
        template=sample_email_template,
    )

    send_to_providers.send_email_to_provider(notification)
    assert mock_get_template.called is False
    assert mock_get_service.called is False
    mock_ses.send_email.assert_called_once_with(
        ANY,
        "test@example.com",
        ANY,
        body=ANY,
        html_body=ANY,
        reply_to_address=notification.reply_to_text,
    )


def test_get_html_email_options_return_email_branding_from_serialised_service(
    sample_service,
):
    branding = create_email_branding()
    sample_service.email_branding = branding
    service = SerialisedService.from_id(sample_service.id)
    email_options = get_html_email_options(service)
    assert email_options is not None
    assert email_options == {
        "govuk_banner": branding.brand_type == BrandType.BOTH,
        "brand_banner": branding.brand_type == BrandType.ORG_BANNER,
        "brand_colour": branding.colour,
        "brand_logo": get_logo_url(current_app.config["ADMIN_BASE_URL"], branding.logo),
        "brand_text": branding.text,
        "brand_name": branding.name,
    }


def test_get_html_email_options_add_email_branding_from_service(sample_service):
    branding = create_email_branding()
    sample_service.email_branding = branding
    email_options = get_html_email_options(sample_service)
    assert email_options is not None
    assert email_options == {
        "govuk_banner": branding.brand_type == BrandType.BOTH,
        "brand_banner": branding.brand_type == BrandType.ORG_BANNER,
        "brand_colour": branding.colour,
        "brand_logo": get_logo_url(current_app.config["ADMIN_BASE_URL"], branding.logo),
        "brand_text": branding.text,
        "brand_name": branding.name,
    }
