import pytest

from app.dao import templates_dao
from app.enums import KeyType, NotificationType, ServicePermissionType, TemplateType
from app.errors import BadRequestError, TotalRequestsError
from app.notifications.process_notifications import create_content_for_notification
from app.notifications.sns_cert_validator import (
    VALID_SNS_TOPICS,
    get_string_to_sign,
    validate_sns_cert,
)
from app.notifications.validators import (
    check_application_over_retention_limit,
    check_if_service_can_send_files_by_email,
    check_is_message_too_long,
    check_notification_content_is_not_empty,
    check_reply_to,
    check_service_email_reply_to_id,
    check_service_over_total_message_limit,
    check_service_sms_sender_id,
    check_template_is_active,
    check_template_is_for_notification_type,
    service_can_send_to_recipient,
    validate_and_format_recipient,
    validate_template,
)
from app.serialised_models import SerialisedService, SerialisedTemplate
from app.service.utils import service_allowed_to_send_to
from app.utils import get_template_instance
from notifications_utils import SMS_CHAR_COUNT_LIMIT
from tests.app.db import (
    create_reply_to_email,
    create_service,
    create_service_guest_list,
    create_service_sms_sender,
    create_template,
)
from tests.conftest import set_config


# all of these tests should have redis enabled (except where we specifically disable it)
@pytest.fixture(scope="module", autouse=True)
def enable_redis(notify_api):
    with set_config(notify_api, "REDIS_ENABLED", True):
        yield


@pytest.mark.parametrize("key_type", [KeyType.TEAM, KeyType.NORMAL])
def test_check_service_over_total_message_limit_fails(
    key_type, mocker, notify_db_session
):
    service = create_service()
    mocker.patch(
        "app.redis_store.get",
        return_value="100001",
    )

    with pytest.raises(TotalRequestsError) as e:
        check_service_over_total_message_limit(key_type, service)
    assert e.value.status_code == 429
    assert e.value.message == "Exceeded total application limits (100000) for today"
    assert e.value.fields == []


@pytest.mark.parametrize("key_type", [KeyType.TEAM, KeyType.NORMAL])
def test_check_application_over_retention_limit_fails(
    key_type, mocker, notify_db_session
):
    service = create_service()
    mocker.patch(
        "app.notifications.validators.dao_get_notification_count_for_service",
        return_value="10001",
    )

    with pytest.raises(TotalRequestsError) as e:
        check_application_over_retention_limit(key_type, service)
    assert e.value.status_code == 429
    assert e.value.message == "Exceeded total application limits (10000) for today"
    assert e.value.fields == []


@pytest.mark.parametrize(
    "template_type, notification_type",
    [
        (TemplateType.EMAIL, NotificationType.EMAIL),
        (TemplateType.SMS, NotificationType.SMS),
    ],
)
def test_check_template_is_for_notification_type_pass(template_type, notification_type):
    assert (
        check_template_is_for_notification_type(
            notification_type=notification_type, template_type=template_type
        )
        is None
    )


@pytest.mark.parametrize(
    "template_type, notification_type",
    [
        (TemplateType.SMS, NotificationType.EMAIL),
        (TemplateType.EMAIL, NotificationType.SMS),
    ],
)
def test_check_template_is_for_notification_type_fails_when_template_type_does_not_match_notification_type(
    template_type, notification_type
):
    with pytest.raises(BadRequestError) as e:
        check_template_is_for_notification_type(
            notification_type=notification_type, template_type=template_type
        )
    assert e.value.status_code == 400
    error_message = (
        f"{template_type} template is not suitable for {notification_type} notification"
    )
    assert e.value.message == error_message
    assert e.value.fields == [{"template": error_message}]


def test_check_template_is_active_passes(sample_template):
    assert check_template_is_active(sample_template) is None


def test_check_template_is_active_fails(sample_template):
    sample_template.archived = True
    from app.dao.templates_dao import dao_update_template

    dao_update_template(sample_template)
    with pytest.raises(BadRequestError) as e:
        check_template_is_active(sample_template)
    assert e.value.status_code == 400
    assert e.value.message == "Template has been deleted"
    assert e.value.fields == [{"template": "Template has been deleted"}]


@pytest.mark.parametrize("key_type", [KeyType.TEST, KeyType.NORMAL])
def test_service_can_send_to_recipient_passes(key_type, notify_db_session):
    trial_mode_service = create_service(service_name="trial mode", restricted=True)
    serialised_service = SerialisedService.from_id(trial_mode_service.id)
    assert (
        service_can_send_to_recipient(
            trial_mode_service.users[0].email_address, key_type, serialised_service
        )
        is None
    )
    assert (
        service_can_send_to_recipient(
            trial_mode_service.users[0].mobile_number, key_type, serialised_service
        )
        is None
    )


@pytest.mark.parametrize(
    "user_number, recipient_number",
    [
        ["+12028675309", "202-867-5309"],
        # ["+447513332413", "+44 (07513) 332413"],
    ],
)
def test_service_can_send_to_recipient_passes_with_non_normalized_number(
    sample_service, user_number, recipient_number
):
    sample_service.users[0].mobile_number = user_number

    serialised_service = SerialisedService.from_id(sample_service.id)

    assert (
        service_can_send_to_recipient(
            recipient_number,
            KeyType.TEAM,
            serialised_service,
        )
        is None
    )


@pytest.mark.parametrize(
    "user_email, recipient_email",
    [
        ["test@example.com", "TeSt@EXAMPLE.com"],
    ],
)
def test_service_can_send_to_recipient_passes_with_non_normalized_email(
    sample_service, user_email, recipient_email
):
    sample_service.users[0].email_address = user_email

    serialised_service = SerialisedService.from_id(sample_service.id)

    assert (
        service_can_send_to_recipient(recipient_email, KeyType.TEAM, serialised_service)
        is None
    )


@pytest.mark.parametrize("key_type", [KeyType.TEST, KeyType.NORMAL])
def test_service_can_send_to_recipient_passes_for_live_service_non_team_member(
    key_type, sample_service
):
    serialised_service = SerialisedService.from_id(sample_service.id)
    assert (
        service_can_send_to_recipient(
            "some_other_email@test.com", key_type, serialised_service
        )
        is None
    )
    assert (
        service_can_send_to_recipient("07513332413", key_type, serialised_service)
        is None
    )


def test_service_can_send_to_recipient_passes_for_guest_list_recipient_passes(
    sample_service,
):
    create_service_guest_list(sample_service, email_address="some_other_email@test.com")
    assert (
        service_can_send_to_recipient(
            "some_other_email@test.com", KeyType.TEAM, sample_service
        )
        is None
    )
    create_service_guest_list(sample_service, mobile_number="2028675309")
    assert (
        service_can_send_to_recipient(
            "2028675309",
            KeyType.TEAM,
            sample_service,
        )
        is None
    )


@pytest.mark.parametrize(
    "recipient",
    [
        {"email_address": "some_other_email@test.com"},
        {"mobile_number": "2028675300"},
    ],
)
def test_service_can_send_to_recipient_fails_when_ignoring_guest_list(
    notify_db_session,
    sample_service,
    recipient,
):
    create_service_guest_list(sample_service, **recipient)
    with pytest.raises(BadRequestError) as exec_info:
        service_can_send_to_recipient(
            next(iter(recipient.values())),
            KeyType.TEAM,
            sample_service,
            allow_guest_list_recipients=False,
        )
    assert exec_info.value.status_code == 400
    assert (
        exec_info.value.message
        == "Can’t send to this recipient using a team-only API key"
    )
    assert exec_info.value.fields == []


@pytest.mark.parametrize("recipient", ["2028675300", "some_other_email@test.com"])
@pytest.mark.parametrize(
    "key_type, error_message",
    [
        (KeyType.TEAM, "Can’t send to this recipient using a team-only API key"),
        (
            KeyType.NORMAL,
            "Can’t send to this recipient when service is in trial mode – see https://www.notifications.service.gov.uk/trial-mode",  # noqa
        ),
    ],
)  # noqa
def test_service_can_send_to_recipient_fails_when_recipient_is_not_on_team(
    recipient,
    key_type,
    error_message,
    notify_db_session,
):
    trial_mode_service = create_service(service_name="trial mode", restricted=True)
    with pytest.raises(BadRequestError) as exec_info:
        service_can_send_to_recipient(recipient, key_type, trial_mode_service)
    assert exec_info.value.status_code == 400
    assert exec_info.value.message == error_message
    assert exec_info.value.fields == []


def test_service_can_send_to_recipient_fails_when_mobile_number_is_not_on_team(
    sample_service,
):
    with pytest.raises(BadRequestError) as e:
        service_can_send_to_recipient("0758964221", KeyType.TEAM, sample_service)
    assert e.value.status_code == 400
    assert e.value.message == "Can’t send to this recipient using a team-only API key"
    assert e.value.fields == []


@pytest.mark.parametrize("char_count", [612, 0, 494, 200, 918])
@pytest.mark.parametrize("show_prefix", [True, False])
@pytest.mark.parametrize("template_type", [TemplateType.SMS, TemplateType.EMAIL])
def test_check_is_message_too_long_passes(
    notify_db_session, show_prefix, char_count, template_type
):
    service = create_service(prefix_sms=show_prefix)
    t = create_template(
        service=service, content="a" * char_count, template_type=template_type
    )
    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=t.id, service_id=service.id
    )
    template_with_content = get_template_instance(template=template.__dict__, values={})
    assert check_is_message_too_long(template_with_content) is None


@pytest.mark.parametrize("char_count", [919, 6000])
@pytest.mark.parametrize("show_prefix", [True, False])
def test_check_is_message_too_long_fails(notify_db_session, show_prefix, char_count):
    with pytest.raises(BadRequestError) as e:
        service = create_service(prefix_sms=show_prefix)
        t = create_template(
            service=service, content="a" * char_count, template_type=TemplateType.SMS
        )
        template = templates_dao.dao_get_template_by_id_and_service_id(
            template_id=t.id, service_id=service.id
        )
        template_with_content = get_template_instance(
            template=template.__dict__, values={}
        )
        check_is_message_too_long(template_with_content)
    assert e.value.status_code == 400
    expected_message = (
        f"Your message is too long. "
        f"Text messages cannot be longer than {SMS_CHAR_COUNT_LIMIT} characters. "
        f"Your message is {char_count} characters long."
    )
    assert e.value.message == expected_message
    assert e.value.fields == []


def test_check_is_message_too_long_passes_for_long_email(sample_service):
    email_character_count = 2_000_001
    t = create_template(
        service=sample_service,
        content="a" * email_character_count,
        template_type=TemplateType.EMAIL,
    )
    template = templates_dao.dao_get_template_by_id_and_service_id(
        template_id=t.id, service_id=t.service_id
    )
    template_with_content = get_template_instance(template=template.__dict__, values={})
    template_with_content.values
    with pytest.raises(BadRequestError) as e:
        check_is_message_too_long(template_with_content)
    assert e.value.status_code == 400
    expected_message = (
        "Your message is too long. "
        + "Emails cannot be longer than 2000000 bytes. "
        + "Your message is 2000001 bytes."
    )
    assert e.value.message == expected_message
    assert e.value.fields == []


def test_check_notification_content_is_not_empty_passes(
    notify_api, mocker, sample_service
):
    template_id = create_template(sample_service, content="Content is not empty").id
    template = SerialisedTemplate.from_id_and_service_id(
        template_id=template_id, service_id=sample_service.id
    )
    template_with_content = create_content_for_notification(template, {})
    assert check_notification_content_is_not_empty(template_with_content) is None


@pytest.mark.parametrize(
    "template_content,notification_values",
    [("", {}), ("((placeholder))", {"placeholder": ""})],
)
def test_check_notification_content_is_not_empty_fails(
    notify_api, mocker, sample_service, template_content, notification_values
):
    template_id = create_template(sample_service, content=template_content).id
    template = SerialisedTemplate.from_id_and_service_id(
        template_id=template_id, service_id=sample_service.id
    )
    template_with_content = create_content_for_notification(
        template, notification_values
    )
    with pytest.raises(BadRequestError) as e:
        check_notification_content_is_not_empty(template_with_content)
    assert e.value.status_code == 400
    assert e.value.message == "Your message is empty."
    assert e.value.fields == []


def test_validate_template(sample_service):
    template = create_template(sample_service, template_type=TemplateType.EMAIL)
    validate_template(template.id, {}, sample_service, NotificationType.EMAIL)


@pytest.mark.parametrize("check_char_count", [True, False])
def test_validate_template_calls_all_validators(
    mocker, fake_uuid, sample_service, check_char_count
):
    template = create_template(sample_service, template_type=TemplateType.EMAIL)
    mock_check_type = mocker.patch(
        "app.notifications.validators.check_template_is_for_notification_type"
    )
    mock_check_if_active = mocker.patch(
        "app.notifications.validators.check_template_is_active"
    )
    mock_create_conent = mocker.patch(
        "app.notifications.validators.create_content_for_notification",
        return_value="content",
    )
    mock_check_not_empty = mocker.patch(
        "app.notifications.validators.check_notification_content_is_not_empty"
    )
    mock_check_message_is_too_long = mocker.patch(
        "app.notifications.validators.check_is_message_too_long"
    )
    template, template_with_content = validate_template(
        template.id,
        {},
        sample_service,
        NotificationType.EMAIL,
        check_char_count=check_char_count,
    )

    mock_check_type.assert_called_once_with(NotificationType.EMAIL, TemplateType.EMAIL)
    mock_check_if_active.assert_called_once_with(template)
    mock_create_conent.assert_called_once_with(template, {})
    mock_check_not_empty.assert_called_once_with("content")
    if check_char_count:
        mock_check_message_is_too_long.assert_called_once_with("content")
    else:
        assert not mock_check_message_is_too_long.called


def test_validate_template_calls_all_validators_exception_message_too_long(
    mocker, fake_uuid, sample_service
):
    template = create_template(sample_service, template_type=TemplateType.EMAIL)
    mock_check_type = mocker.patch(
        "app.notifications.validators.check_template_is_for_notification_type"
    )
    mock_check_if_active = mocker.patch(
        "app.notifications.validators.check_template_is_active"
    )
    mock_create_conent = mocker.patch(
        "app.notifications.validators.create_content_for_notification",
        return_value="content",
    )
    mock_check_not_empty = mocker.patch(
        "app.notifications.validators.check_notification_content_is_not_empty"
    )
    mock_check_message_is_too_long = mocker.patch(
        "app.notifications.validators.check_is_message_too_long"
    )
    template, template_with_content = validate_template(
        template.id,
        {},
        sample_service,
        NotificationType.EMAIL,
        check_char_count=False,
    )

    mock_check_type.assert_called_once_with(NotificationType.EMAIL, TemplateType.EMAIL)
    mock_check_if_active.assert_called_once_with(template)
    mock_create_conent.assert_called_once_with(template, {})
    mock_check_not_empty.assert_called_once_with("content")
    assert not mock_check_message_is_too_long.called


@pytest.mark.parametrize("key_type", [KeyType.TEST, KeyType.NORMAL])
def test_validate_and_format_recipient_fails_when_international_number_and_service_does_not_allow_int_sms(
    key_type,
    notify_db_session,
):
    service = create_service(service_permissions=[ServicePermissionType.SMS])
    service_model = SerialisedService.from_id(service.id)
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient(
            "+20-12-1234-1234",
            key_type,
            service_model,
            NotificationType.SMS,
        )
    assert e.value.status_code == 400
    assert e.value.message == "Cannot send to international mobile numbers"
    assert e.value.fields == []


@pytest.mark.parametrize("key_type", [KeyType.TEST, KeyType.NORMAL])
def test_validate_and_format_recipient_succeeds_with_international_numbers_if_service_does_allow_int_sms(
    key_type, sample_service_full_permissions
):
    service_model = SerialisedService.from_id(sample_service_full_permissions.id)
    result = validate_and_format_recipient(
        "+4407513332413", key_type, service_model, NotificationType.SMS
    )
    assert result == "+447513332413"


def test_validate_and_format_recipient_fails_when_no_recipient():
    with pytest.raises(BadRequestError) as e:
        validate_and_format_recipient(
            None,
            KeyType.NORMAL,
            "service",
            NotificationType.SMS,
        )
    assert e.value.status_code == 400
    assert e.value.message == "Recipient can't be empty"


@pytest.mark.parametrize(
    "notification_type",
    [NotificationType.SMS, NotificationType.EMAIL],
)
def test_check_service_email_reply_to_id_where_reply_to_id_is_none(notification_type):
    assert check_service_email_reply_to_id(None, None, notification_type) is None


def test_check_service_email_reply_to_where_email_reply_to_is_found(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert (
        check_service_email_reply_to_id(
            sample_service.id, reply_to_address.id, NotificationType.EMAIL
        )
        == "test@test.com"
    )


def test_check_service_email_reply_to_id_where_service_id_is_not_found(
    sample_service, fake_uuid
):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(
            fake_uuid, reply_to_address.id, NotificationType.EMAIL
        )
    assert e.value.status_code == 400
    assert e.value.message == (
        f"email_reply_to_id {reply_to_address.id} does not exist in database for "
        f"service id {fake_uuid}"
    )


def test_check_service_email_reply_to_id_where_reply_to_id_is_not_found(
    sample_service, fake_uuid
):
    with pytest.raises(BadRequestError) as e:
        check_service_email_reply_to_id(
            sample_service.id, fake_uuid, NotificationType.EMAIL
        )
    assert e.value.status_code == 400
    assert e.value.message == (
        f"email_reply_to_id {fake_uuid} does not exist in database for service "
        f"id {sample_service.id}"
    )


@pytest.mark.parametrize(
    "notification_type",
    [NotificationType.SMS, NotificationType.EMAIL],
)
def test_check_service_sms_sender_id_where_sms_sender_id_is_none(notification_type):
    assert check_service_sms_sender_id(None, None, notification_type) is None


def test_check_service_sms_sender_id_where_sms_sender_id_is_found(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    assert (
        check_service_sms_sender_id(
            sample_service.id,
            sms_sender.id,
            NotificationType.SMS,
        )
        == "123456"
    )


def test_check_service_sms_sender_id_where_service_id_is_not_found(
    sample_service, fake_uuid
):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(fake_uuid, sms_sender.id, NotificationType.SMS)
    assert e.value.status_code == 400
    assert e.value.message == (
        f"sms_sender_id {sms_sender.id} does not exist in database for service "
        f"id {fake_uuid}"
    )


def test_check_service_sms_sender_id_where_sms_sender_is_not_found(
    sample_service, fake_uuid
):
    with pytest.raises(BadRequestError) as e:
        check_service_sms_sender_id(sample_service.id, fake_uuid, NotificationType.SMS)
    assert e.value.status_code == 400
    assert e.value.message == (
        f"sms_sender_id {fake_uuid} does not exist in database for service "
        f"id {sample_service.id}"
    )


@pytest.mark.parametrize(
    "notification_type",
    [NotificationType.SMS, NotificationType.EMAIL],
)
def test_check_reply_to_with_empty_reply_to(sample_service, notification_type):
    assert check_reply_to(sample_service.id, None, notification_type) is None


def test_check_reply_to_email_type(sample_service):
    reply_to_address = create_reply_to_email(sample_service, "test@test.com")
    assert (
        check_reply_to(sample_service.id, reply_to_address.id, NotificationType.EMAIL)
        == "test@test.com"
    )


def test_check_reply_to_sms_type(sample_service):
    sms_sender = create_service_sms_sender(service=sample_service, sms_sender="123456")
    assert (
        check_reply_to(sample_service.id, sms_sender.id, NotificationType.SMS)
        == "123456"
    )


def test_check_if_service_can_send_files_by_email_raises_if_no_contact_link_set(
    sample_service,
):
    with pytest.raises(BadRequestError) as e:
        check_if_service_can_send_files_by_email(
            service_contact_link=sample_service.contact_link,
            service_id=sample_service.id,
        )

    message = (
        f"Send files by email has not been set up - add contact details for your service at "
        f"http://localhost:6012/services/{sample_service.id}/service-settings/send-files-by-email"
    )
    assert e.value.status_code == 400
    assert e.value.message == message


def test_check_if_service_can_send_files_by_email_passes_if_contact_link_set(
    sample_service,
):
    sample_service.contact_link = "contact.me@gov.uk"
    check_if_service_can_send_files_by_email(
        service_contact_link=sample_service.contact_link, service_id=sample_service.id
    )


def test_get_string_to_sign():
    VALID_SNS_TOPICS.append("arn:aws:sns:us-west-2:009969138378:connector-svc-test")
    sns_payload = {
        "Type": "Notification",
        "MessageId": "ccccccccc-cccc-cccc-cccc-ccccccccccccc",
        "TopicArn": "arn:aws:sns:us-west-2:009969138378:connector-svc-test",
        "Message": '{"AbsoluteTime":"2021-09-08T13:28:24.656Z","Content":"help","ContentType":"text/plain","Id":"333333333-be0d-4a44-889d-d2a86fc06f0c","Type":"MESSAGE","ParticipantId":"bbbbbbbb-c562-4d95-b76c-dcbca8b4b5f7","DisplayName":"Jane","ParticipantRole":"CUSTOMER","InitialContactId":"33333333-abc5-46db-9ad5-d772559ab556","ContactId":"33333333-abc5-46db-9ad5-d772559ab556"}',  # noqa
        "Timestamp": "2021-09-08T13:28:24.860Z",
        "SignatureVersion": "1",
        "Signature": "examplegggggg/1tEBYdiVDgJgBoJUniUFcArLFGfg5JCvpOr/v6LPCHiD7A0BWy8+ZOnGTmOjBMn80U9jSzYhKbHDbQHaNYTo9sRyQA31JtHHiIseQeMfTDpcaAXqfs8hdIXq4XZaJYqDFqosfbvh56VPh5QgmeHTltTc7eOZBUwnt/177eOTLTt2yB0ItMV3NAYuE1Tdxya1lLYZQUIMxETTVcRAZkDIu8TbRZC9a00q2RQVjXhDaU3k+tL+kk85syW/2ryjjkDYoUb+dyRGkqMy4aKA22UpfidOtdAZ/GGtXaXSKBqazZTEUuSEzt0duLtFntQiYJanU05gtDig==",  # noqa
        "SigningCertURL": "https://sns.us-west-2.amazonaws.com/SimpleNotificationService-11111111111111111111111111111111.pem",  # noqa
        "UnsubscribeURL": "https://sns.us-west-2.amazonaws.com/?Action=Unsubscribe&SubscriptionArn=arn:aws:sns:us-west-2:000000000000:connector-svc-test:22222222-aaaa-bbbb-cccc-333333333333",  # noqa
        "MessageAttributes": {
            "InitialContactId": {
                "Type": "String",
                "Value": "33333333-abc5-46db-9ad5-d772559ab556",
            },
            "MessageVisibility": {"Type": "String", "Value": "ALL"},
            "Type": {"Type": "String", "Value": "MESSAGE"},
            "AccountId": {"Type": "String", "Value": "999999999999"},
            "ContentType": {"Type": "String", "Value": "text/plain"},
            "InstanceId": {
                "Type": "String",
                "Value": "dddddddd-b64e-40c5-921b-109fd92499ae",
            },
            "ContactId": {
                "Type": "String",
                "Value": "33333333-abc5-46db-9ad5-d772559ab556",
            },
            "ParticipantRole": {"Type": "String", "Value": "CUSTOMER"},
        },
    }
    str = get_string_to_sign(sns_payload)
    assert (
        str
        == b'Message\n{"AbsoluteTime":"2021-09-08T13:28:24.656Z","Content":"help","ContentType":"text/plain","Id":"333333333-be0d-4a44-889d-d2a86fc06f0c","Type":"MESSAGE","ParticipantId":"bbbbbbbb-c562-4d95-b76c-dcbca8b4b5f7","DisplayName":"Jane","ParticipantRole":"CUSTOMER","InitialContactId":"33333333-abc5-46db-9ad5-d772559ab556","ContactId":"33333333-abc5-46db-9ad5-d772559ab556"}\nMessageId\nccccccccc-cccc-cccc-cccc-ccccccccccccc\nTimestamp\n2021-09-08T13:28:24.860Z\nTopicArn\narn:aws:sns:us-west-2:009969138378:connector-svc-test\nType\nNotification\n'  # noqa
    )

    # This is a test payload with no valid cert, so it should raise a ValueError
    with pytest.raises(ValueError):
        validate_sns_cert(sns_payload)


def test_check_service_over_total_message_limit(mocker, sample_service):
    get_redis_mock = mocker.patch("app.notifications.validators.redis_store.get")
    get_redis_mock.return_value = None
    service_stats = check_service_over_total_message_limit(
        KeyType.NORMAL,
        sample_service,
    )
    assert service_stats == 0


def test_service_allowed_to_send_to_simulated_numbers():
    trial_mode_service = create_service(service_name="trial mode", restricted=True)
    can_send = service_allowed_to_send_to(
        "+14254147755",
        trial_mode_service,
        KeyType.NORMAL,
        allow_guest_list_recipients=True,
    )
    can_not_send = service_allowed_to_send_to(
        "+15555555555",
        trial_mode_service,
        KeyType.NORMAL,
        allow_guest_list_recipients=True,
    )
    assert can_send is True
    assert can_not_send is False
