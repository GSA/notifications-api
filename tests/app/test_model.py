import pytest
from freezegun import freeze_time
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db, encryption
from app.enums import (
    AgreementStatus,
    AgreementType,
    AuthType,
    NotificationStatus,
    NotificationType,
    RecipientType,
    TemplateType,
)
from app.models import (
    Agreement,
    AnnualBilling,
    Notification,
    NotificationHistory,
    Service,
    ServiceGuestList,
    ServicePermission,
    User,
    VerifyCode,
    filter_null_value_fields,
)
from app.utils import utc_now
from tests.app.db import (
    create_inbound_number,
    create_notification,
    create_organization,
    create_rate,
    create_reply_to_email,
    create_service,
    create_service_guest_list,
    create_template,
    create_template_folder,
)


@pytest.mark.parametrize("mobile_number", ["+14254147755", "+12348675309"])
def test_should_build_service_guest_list_from_mobile_number(mobile_number):
    service_guest_list = ServiceGuestList.from_string(
        "service_id",
        RecipientType.MOBILE,
        mobile_number,
    )

    assert service_guest_list.recipient == mobile_number


@pytest.mark.parametrize("email_address", ["test@example.com"])
def test_should_build_service_guest_list_from_email_address(email_address):
    service_guest_list = ServiceGuestList.from_string(
        "service_id",
        RecipientType.EMAIL,
        email_address,
    )

    assert service_guest_list.recipient == email_address


@pytest.mark.parametrize(
    "contact, recipient_type",
    [
        ("", None),
        ("07700dsadsad", RecipientType.MOBILE),
        ("gmail.com", RecipientType.EMAIL),
    ],
)
def test_should_not_build_service_guest_list_from_invalid_contact(
    recipient_type, contact
):
    with pytest.raises(ValueError):
        ServiceGuestList.from_string("service_id", recipient_type, contact)


@pytest.mark.parametrize(
    "initial_statuses, expected_statuses",
    [
        # passing in single statuses as strings
        (NotificationStatus.FAILED, NotificationStatus.failed_types()),
        (NotificationStatus.CREATED, [NotificationStatus.CREATED]),
        (NotificationStatus.TECHNICAL_FAILURE, [NotificationStatus.TECHNICAL_FAILURE]),
        # passing in lists containing single statuses
        ([NotificationStatus.FAILED], NotificationStatus.failed_types()),
        ([NotificationStatus.CREATED], [NotificationStatus.CREATED]),
        (
            [NotificationStatus.TECHNICAL_FAILURE],
            [NotificationStatus.TECHNICAL_FAILURE],
        ),
        # passing in lists containing multiple statuses
        (
            [NotificationStatus.FAILED, NotificationStatus.CREATED],
            list(NotificationStatus.failed_types()) + [NotificationStatus.CREATED],
        ),
        (
            [NotificationStatus.CREATED, NotificationStatus.PENDING],
            [NotificationStatus.CREATED, NotificationStatus.PENDING],
        ),
        (
            [NotificationStatus.CREATED, NotificationStatus.TECHNICAL_FAILURE],
            [NotificationStatus.CREATED, NotificationStatus.TECHNICAL_FAILURE],
        ),
        # checking we don't end up with duplicates
        (
            [
                NotificationStatus.FAILED,
                NotificationStatus.CREATED,
                NotificationStatus.TECHNICAL_FAILURE,
            ],
            list(NotificationStatus.failed_types()) + [NotificationStatus.CREATED],
        ),
    ],
)
def test_status_conversion(initial_statuses, expected_statuses):
    converted_statuses = Notification.substitute_status(initial_statuses)
    assert len(converted_statuses) == len(expected_statuses)
    assert set(converted_statuses) == set(expected_statuses)


@freeze_time("2016-01-01 11:09:00.000000")
@pytest.mark.parametrize(
    "template_type, recipient",
    [
        (TemplateType.SMS, "+12028675309"),
        (TemplateType.EMAIL, "foo@bar.com"),
    ],
)
def test_notification_for_csv_returns_correct_type(
    sample_service, template_type, recipient
):
    template = create_template(sample_service, template_type=template_type)
    notification = create_notification(template, to_field=recipient)

    serialized = notification.serialize_for_csv()
    assert serialized["template_type"] == template_type


@freeze_time("2016-01-01 11:09:00.000000")
def test_notification_for_csv_returns_correct_job_row_number(sample_job):
    notification = create_notification(
        sample_job.template, sample_job, job_row_number=0
    )

    serialized = notification.serialize_for_csv()
    assert serialized["row_number"] == 1


@freeze_time("2016-01-30 12:39:58.321312")
@pytest.mark.parametrize(
    "template_type, status, expected_status",
    [
        (TemplateType.EMAIL, NotificationStatus.FAILED, "Failed"),
        (TemplateType.EMAIL, NotificationStatus.TECHNICAL_FAILURE, "Technical failure"),
        (
            TemplateType.EMAIL,
            NotificationStatus.TEMPORARY_FAILURE,
            "Inbox not accepting messages right now",
        ),
        (
            TemplateType.EMAIL,
            NotificationStatus.PERMANENT_FAILURE,
            "Email address doesn’t exist",
        ),
        (
            TemplateType.SMS,
            NotificationStatus.TEMPORARY_FAILURE,
            "Unable to find carrier response -- still looking",
        ),
        (
            TemplateType.SMS,
            NotificationStatus.PERMANENT_FAILURE,
            "Unable to find carrier response.",
        ),
        (TemplateType.SMS, NotificationStatus.SENT, "Sent internationally"),
    ],
)
def test_notification_for_csv_returns_formatted_status(
    sample_service, template_type, status, expected_status
):
    template = create_template(sample_service, template_type=template_type)
    notification = create_notification(template, status=status)

    serialized = notification.serialize_for_csv()
    assert serialized["status"] == expected_status


@freeze_time("2017-03-26 23:01:53.321312")
def test_notification_for_csv_returns_utc_correctly(sample_template):
    notification = create_notification(sample_template)

    serialized = notification.serialize_for_csv()
    assert serialized["created_at"] == "2017-03-26 23:01:53"


def test_notification_personalisation_getter_returns_empty_dict_from_none():
    noti = Notification()
    noti._personalisation = None
    assert noti.personalisation == {}


def test_notification_personalisation_getter_always_returns_empty_dict(notify_app):
    noti = Notification()
    noti._personalisation = encryption.encrypt({})
    assert noti.personalisation == {}


def test_notification_personalisation_getter_returns_empty_dict_for_encryption_errors(
    notify_app,
):
    noti = Notification()
    # old _personalisation values were created with encryption.sign, which will trigger a decryption error
    noti._personalisation = encryption.sign({"value": "PII"})
    assert noti.personalisation == {}


@pytest.mark.parametrize("input_value", [None, {}])
def test_notification_personalisation_setter_always_sets_empty_dict(
    notify_app, input_value
):
    noti = Notification()
    noti.personalisation = input_value

    assert noti.personalisation == {}


def test_notification_subject_is_none_for_sms(sample_service):
    template = create_template(service=sample_service, template_type=TemplateType.SMS)
    notification = create_notification(template=template)
    assert notification.subject is None


@pytest.mark.parametrize("template_type", [TemplateType.EMAIL])
def test_notification_subject_fills_in_placeholders(sample_service, template_type):
    template = create_template(
        service=sample_service, template_type=template_type, subject="((name))"
    )
    notification = create_notification(
        template=template, personalisation={"name": "hello"}
    )
    assert notification.subject == "hello"


def test_notification_serializes_created_by_name_with_no_created_by_id(
    client, sample_notification
):
    res = sample_notification.serialize()
    assert res["created_by_name"] is None


def test_notification_serializes_created_by_name_with_created_by_id(
    client, sample_notification, sample_user
):
    sample_notification.created_by_id = sample_user.id
    res = sample_notification.serialize()
    assert res["created_by_name"] == sample_user.name


def test_sms_notification_serializes_without_subject(client, sample_template):
    res = sample_template.serialize_for_v2()
    assert res["subject"] is None


def test_email_notification_serializes_with_subject(client, sample_email_template):
    res = sample_email_template.serialize_for_v2()
    assert res["subject"] == "Email Subject"


def test_notification_references_template_history(client, sample_template):
    noti = create_notification(sample_template)
    sample_template.version = 3
    sample_template.content = "New template content"

    res = noti.serialize()
    assert res["template"]["version"] == 1

    assert res["body"] == noti.template.content
    assert noti.template.content != sample_template.content


def test_notification_requires_a_valid_template_version(client, sample_template):
    sample_template.version = 2
    with pytest.raises(IntegrityError):
        create_notification(sample_template)


def test_inbound_number_serializes_with_service(client, notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number(number="1", service_id=service.id)
    serialized_inbound_number = inbound_number.serialize()
    assert serialized_inbound_number.get("id") == str(inbound_number.id)
    assert serialized_inbound_number.get("service").get("id") == str(
        inbound_number.service.id
    )
    assert (
        serialized_inbound_number.get("service").get("name")
        == inbound_number.service.name
    )


def test_inbound_number_returns_inbound_number(client, notify_db_session):
    service = create_service()
    inbound_number = create_inbound_number(number="1", service_id=service.id)

    assert service.get_inbound_number() == inbound_number.number


def test_inbound_number_returns_none_when_no_inbound_number(client, notify_db_session):
    service = create_service()

    assert not service.get_inbound_number()


def test_service_get_default_reply_to_email_address(sample_service):
    create_reply_to_email(service=sample_service, email_address="default@email.com")

    assert sample_service.get_default_reply_to_email_address() == "default@email.com"


def test_service_get_default_sms_sender(notify_db_session):
    service = create_service()
    assert service.get_default_sms_sender() == "testing"


def test_template_folder_is_parent(sample_service):
    x = None
    folders = []
    for i in range(5):
        x = create_template_folder(sample_service, name=str(i), parent=x)
        folders.append(x)

    assert folders[0].is_parent_of(folders[1])
    assert folders[0].is_parent_of(folders[2])
    assert folders[0].is_parent_of(folders[4])
    assert folders[1].is_parent_of(folders[2])
    assert not folders[1].is_parent_of(folders[0])


@pytest.mark.parametrize("is_platform_admin", (False, True))
def test_user_can_use_webauthn_if_platform_admin(sample_user, is_platform_admin):
    sample_user.platform_admin = is_platform_admin
    assert sample_user.can_use_webauthn == is_platform_admin


@pytest.mark.parametrize(
    ("auth_type", "can_use_webauthn"),
    [(AuthType.EMAIL, False), (AuthType.SMS, False), (AuthType.WEBAUTHN, True)],
)
def test_user_can_use_webauthn_if_they_login_with_it(
    sample_user, auth_type, can_use_webauthn
):
    sample_user.auth_type = auth_type
    assert sample_user.can_use_webauthn == can_use_webauthn


def test_user_can_use_webauthn_if_in_notify_team(notify_service):
    assert notify_service.users[0].can_use_webauthn


@pytest.mark.parametrize(
    ("obj", "return_val"),
    [
        ({"a": None}, {}),
        ({"b": 123}, {"b": 123}),
        ({"c": None, "d": 456}, {"d": 456}),
        ({}, {}),
    ],
)
def test_filter_null_value_fields(obj, return_val):
    assert return_val == filter_null_value_fields(obj)


def test_user_validate_mobile_number():
    user = User()
    with pytest.raises(ValueError):
        user.validate_mobile_number("somekey", "abcde")


def test_user_password():
    user = User()
    with pytest.raises(AttributeError):
        user.password()


def test_annual_billing_serialize():
    now = utc_now()
    ab = AnnualBilling()
    service = Service()
    ab.service = service
    ab.created_at = now
    serialized = ab.serialize()
    print(serialized)
    expected_keys = [
        "id",
        "free_sms_fragment_limit",
        "service_id",
        "financial_year_start",
        "created_at",
        "updated_at",
        "service",
    ]
    for key in expected_keys:
        assert key in serialized
        serialized.pop(key)
    assert serialized == {}


def test_repr():
    service = create_service()
    sps = db.session.execute(select(ServicePermission)).scalars().all()
    for sp in sps:
        assert "has service permission" in sp.__repr__()

    sgl = create_service_guest_list(service)
    assert sgl.__repr__() == "Recipient guest_list_user@digital.fake.gov of type: email"


def test_verify_code():
    vc = VerifyCode()
    with pytest.raises(AttributeError):
        vc.code()


def test_notification_get_created_by_email_address(sample_notification, sample_user):
    sample_notification.created_by_id = sample_user.id
    assert (
        sample_notification.get_created_by_email_address() == "notify@digital.fake.gov"
    )


def test_notification_history_from_original(sample_notification):
    history = NotificationHistory.from_original(sample_notification)
    assert isinstance(history, NotificationHistory)


def test_rate_str():
    rate = create_rate("2023-01-01 00:00:00", 1.5, NotificationType.SMS)

    assert rate.__str__() == "1.5 sms 2023-01-01 00:00:00"


@pytest.mark.parametrize(
    ["agreement_type", "expected"],
    (
        (AgreementType.IAA, False),
        (AgreementType.MOU, True),
    ),
)
def test_organization_agreement_mou(notify_db_session, agreement_type, expected):
    now = utc_now()
    agree = Agreement()
    agree.id = "whatever"
    agree.start_time = now
    agree.end_time = now
    agree.status = AgreementStatus.ACTIVE
    agree.type = agreement_type
    organization = create_organization(name="Something")
    organization.agreements.append(agree)
    assert organization.has_mou == expected


@pytest.mark.parametrize(
    ["agreement_status", "expected"],
    (
        (AgreementStatus.EXPIRED, False),
        (AgreementStatus.ACTIVE, True),
    ),
)
def test_organization_agreement_active(notify_db_session, agreement_status, expected):
    now = utc_now()
    agree = Agreement()
    agree.id = "whatever"
    agree.start_time = now
    agree.end_time = now
    agree.status = agreement_status
    agree.type = AgreementType.IAA
    organization = create_organization(name="Something")
    organization.agreements.append(agree)
    assert organization.agreement_active == expected


def test_agreement_serialize():
    agree = Agreement()
    agree.id = "abc"

    now = utc_now()
    agree.start_time = now
    agree.end_time = now
    serialize = agree.serialize()
    serialize.pop("start_time")
    serialize.pop("end_time")
    assert serialize == {
        "id": "abc",
        "type": None,
        "partner_name": None,
        "status": None,
        "budget_amount": None,
        "organization_id": None,
    }
