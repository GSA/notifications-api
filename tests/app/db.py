import random
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select

from app import db
from app.dao import fact_processing_time_dao
from app.dao.email_branding_dao import dao_create_email_branding
from app.dao.inbound_sms_dao import dao_create_inbound_sms
from app.dao.invited_org_user_dao import save_invited_org_user
from app.dao.invited_user_dao import save_invited_user
from app.dao.jobs_dao import dao_create_job
from app.dao.notifications_dao import dao_create_notification
from app.dao.organization_dao import (
    dao_add_service_to_organization,
    dao_create_organization,
)
from app.dao.permissions_dao import permission_dao
from app.dao.service_callback_api_dao import save_service_callback_api
from app.dao.service_data_retention_dao import insert_service_data_retention
from app.dao.service_inbound_api_dao import save_service_inbound_api
from app.dao.service_permissions_dao import dao_add_service_permission
from app.dao.service_sms_sender_dao import (
    dao_update_service_sms_sender,
    update_existing_sms_sender_with_inbound_number,
)
from app.dao.services_dao import dao_add_user_to_service, dao_create_service
from app.dao.templates_dao import dao_create_template, dao_update_template
from app.dao.users_dao import save_model_user
from app.enums import (
    CallbackType,
    JobStatus,
    KeyType,
    NotificationStatus,
    NotificationType,
    OrganizationType,
    RecipientType,
    ServicePermissionType,
    TemplateProcessType,
    TemplateType,
)
from app.models import (
    AnnualBilling,
    ApiKey,
    Complaint,
    Domain,
    EmailBranding,
    FactBilling,
    FactNotificationStatus,
    FactProcessingTime,
    InboundNumber,
    InboundSms,
    InvitedOrganizationUser,
    InvitedUser,
    Job,
    Notification,
    NotificationHistory,
    Organization,
    Permission,
    Rate,
    Service,
    ServiceCallbackApi,
    ServiceEmailReplyTo,
    ServiceGuestList,
    ServiceInboundApi,
    ServicePermission,
    ServiceSmsSender,
    Template,
    TemplateFolder,
    User,
    WebauthnCredential,
)
from app.utils import utc_now


def create_user(
    *,
    mobile_number="+12028675309",
    email=None,
    state="active",
    id_=None,
    name="Test User",
    platform_admin=False,
    login_uuid=None,
):
    data = {
        "id": id_ or uuid.uuid4(),
        "name": name,
        "email_address": email or f"{uuid.uuid4()}@test.gsa.gov",
        "password": "password",
        "mobile_number": mobile_number,
        "state": state,
        "platform_admin": platform_admin,
        "login_uuid": login_uuid,
    }
    stmt = select(User).where(User.email_address == email)
    user = db.session.execute(stmt).scalars().first()
    if not user:
        user = User(**data)
    save_model_user(user, validated_email_access=True)
    return user


def create_permissions(user, service, *permissions):
    permissions = [
        Permission(service_id=service.id, user_id=user.id, permission=p)
        for p in permissions
    ]

    permission_dao.set_user_service_permission(user, service, permissions, _commit=True)


def create_service(
    user=None,
    service_name="Sample service",
    service_id=None,
    restricted=False,
    count_as_live=True,
    service_permissions=None,
    research_mode=False,
    active=True,
    email_from=None,
    prefix_sms=True,
    message_limit=1000,
    total_message_limit=100000,
    organization_type=OrganizationType.FEDERAL,
    check_if_service_exists=False,
    go_live_user=None,
    go_live_at=None,
    organization=None,
    purchase_order_number=None,
    billing_contact_names=None,
    billing_contact_email_addresses=None,
    billing_reference=None,
):
    if check_if_service_exists:
        stmt = select(Service).where(Service.name == service_name)
        service = db.session.execute(stmt).scalars().first()
    if (not check_if_service_exists) or (check_if_service_exists and not service):
        service = Service(
            name=service_name,
            message_limit=message_limit,
            total_message_limit=total_message_limit,
            restricted=restricted,
            email_from=(
                email_from if email_from else service_name.lower().replace(" ", ".")
            ),
            created_by=(
                user
                if user
                else create_user(email="{}@test.gsa.gov".format(uuid.uuid4()))
            ),
            prefix_sms=prefix_sms,
            organization_type=organization_type,
            organization=organization,
            go_live_user=go_live_user,
            go_live_at=go_live_at,
            purchase_order_number=purchase_order_number,
            billing_contact_names=billing_contact_names,
            billing_contact_email_addresses=billing_contact_email_addresses,
            billing_reference=billing_reference,
        )
        dao_create_service(
            service,
            service.created_by,
            service_id,
            service_permissions=service_permissions,
        )

        service.active = active
        service.research_mode = research_mode
        service.count_as_live = count_as_live
    else:
        if user and user not in service.users:
            dao_add_user_to_service(service, user)

    return service


def create_service_with_inbound_number(inbound_number="1234567", *args, **kwargs):
    service = create_service(*args, **kwargs)

    stmt = select(ServiceSmsSender).where(ServiceSmsSender.service_id == service.id)
    sms_sender = db.session.execute(stmt).scalars().first()
    inbound = create_inbound_number(number=inbound_number, service_id=service.id)
    update_existing_sms_sender_with_inbound_number(
        service_sms_sender=sms_sender,
        sms_sender=inbound_number,
        inbound_number_id=inbound.id,
    )

    return service


def create_service_with_defined_sms_sender(sms_sender_value="1234567", *args, **kwargs):
    service = create_service(*args, **kwargs)

    stmt = select(ServiceSmsSender).where(ServiceSmsSender.service_id == service.id)
    sms_sender = db.session.execute(stmt).scalars().first()
    dao_update_service_sms_sender(
        service_id=service.id,
        service_sms_sender_id=sms_sender.id,
        is_default=True,
        sms_sender=sms_sender_value,
    )

    return service


def create_template(
    service,
    template_type=TemplateType.SMS,
    template_name=None,
    subject="Template subject",
    content="Dear Sir/Madam, Hello. Yours Truly, The Government.",
    reply_to=None,
    hidden=False,
    archived=False,
    folder=None,
    process_type=TemplateProcessType.NORMAL,
    contact_block_id=None,
):
    data = {
        "name": template_name or f"{template_type} Template Name",
        "template_type": template_type,
        "content": content,
        "service": service,
        "created_by": service.created_by,
        "reply_to": reply_to,
        "hidden": hidden,
        "folder": folder,
        "process_type": process_type,
    }
    if template_type != TemplateType.SMS:
        data["subject"] = subject
    template = Template(**data)
    dao_create_template(template)

    if archived:
        template.archived = archived
        dao_update_template(template)

    return template


def create_notification(
    template=None,
    job=None,
    job_row_number=None,
    to_field=None,
    status=NotificationStatus.CREATED,
    reference=None,
    created_at=None,
    sent_at=None,
    updated_at=None,
    billable_units=1,
    personalisation=None,
    api_key=None,
    key_type=KeyType.NORMAL,
    sent_by=None,
    client_reference=None,
    rate_multiplier=None,
    international=False,
    phone_prefix=None,
    normalised_to=None,
    one_off=False,
    reply_to_text=None,
    created_by_id=None,
    document_download_count=None,
):
    assert job or template
    if job:
        template = job.template

    if created_at is None:
        created_at = utc_now()

    if to_field is None:
        to_field = (
            "+447700900855"
            if template.template_type == TemplateType.SMS
            else "test@example.com"
        )

    if status not in (
        NotificationStatus.CREATED,
        NotificationStatus.VALIDATION_FAILED,
        NotificationStatus.VIRUS_SCAN_FAILED,
        NotificationStatus.PENDING_VIRUS_CHECK,
    ):
        sent_at = sent_at or utc_now()
        updated_at = updated_at or utc_now()

    if not one_off and (job is None and api_key is None):
        # we did not specify in test - lets create it
        stmt = select(ApiKey).where(
            ApiKey.service == template.service, ApiKey.key_type == key_type
        )
        api_key = db.session.execute(stmt).scalars().first()
        if not api_key:
            api_key = create_api_key(template.service, key_type=key_type)

    data = {
        "id": uuid.uuid4(),
        "to": to_field,
        "job_id": job and job.id,
        "job": job,
        "service_id": template.service.id,
        "service": template.service,
        "template_id": template.id,
        "template_version": template.version,
        "status": status,
        "reference": reference,
        "created_at": created_at,
        "sent_at": sent_at,
        "billable_units": billable_units,
        "personalisation": personalisation,
        "notification_type": template.template_type,
        "api_key": api_key,
        "api_key_id": api_key and api_key.id,
        "key_type": api_key.key_type if api_key else key_type,
        "sent_by": sent_by,
        "updated_at": updated_at,
        "client_reference": client_reference,
        "job_row_number": job_row_number,
        "rate_multiplier": rate_multiplier,
        "international": international,
        "phone_prefix": phone_prefix,
        "normalised_to": normalised_to,
        "reply_to_text": reply_to_text,
        "created_by_id": created_by_id,
        "document_download_count": document_download_count,
    }
    notification = Notification(**data)
    dao_create_notification(notification)
    notification.personalisation = personalisation

    return notification


def create_notification_history(
    template=None,
    job=None,
    job_row_number=None,
    status=NotificationStatus.CREATED,
    reference=None,
    created_at=None,
    sent_at=None,
    updated_at=None,
    billable_units=1,
    api_key=None,
    key_type=KeyType.NORMAL,
    sent_by=None,
    client_reference=None,
    rate_multiplier=None,
    international=False,
    phone_prefix=None,
    created_by_id=None,
    id=None,
):
    assert job or template
    if job:
        template = job.template

    if created_at is None:
        created_at = utc_now()

    if status != NotificationStatus.CREATED:
        sent_at = sent_at or utc_now()
        updated_at = updated_at or utc_now()

    data = {
        "id": id or uuid.uuid4(),
        "job_id": job and job.id,
        "job": job,
        "service_id": template.service.id,
        "service": template.service,
        "template_id": template.id,
        "template_version": template.version,
        "status": status,
        "reference": reference,
        "created_at": created_at,
        "sent_at": sent_at,
        "billable_units": billable_units,
        "notification_type": template.template_type,
        "api_key": api_key,
        "api_key_id": api_key and api_key.id,
        "key_type": api_key.key_type if api_key else key_type,
        "sent_by": sent_by,
        "updated_at": updated_at,
        "client_reference": client_reference,
        "job_row_number": job_row_number,
        "rate_multiplier": rate_multiplier,
        "international": international,
        "phone_prefix": phone_prefix,
        "created_by_id": created_by_id,
    }
    notification_history = NotificationHistory(**data)
    db.session.add(notification_history)
    db.session.commit()

    return notification_history


def create_job(
    template,
    notification_count=1,
    created_at=None,
    job_status=JobStatus.PENDING,
    scheduled_for=None,
    processing_started=None,
    processing_finished=None,
    original_file_name="some.csv",
    archived=False,
):
    data = {
        "id": uuid.uuid4(),
        "service_id": template.service_id,
        "service": template.service,
        "template_id": template.id,
        "template_version": template.version,
        "original_file_name": original_file_name,
        "notification_count": notification_count,
        "created_at": created_at or utc_now(),
        "created_by": template.created_by,
        "job_status": job_status,
        "scheduled_for": scheduled_for,
        "processing_started": processing_started,
        "processing_finished": processing_finished,
        "archived": archived,
    }
    job = Job(**data)
    dao_create_job(job)
    return job


def create_service_permission(service_id, permission=ServicePermissionType.EMAIL):
    dao_add_service_permission(
        service_id if service_id else create_service().id,
        permission,
    )

    service_permissions = db.session.execute(select(ServicePermission)).scalars().all()

    return service_permissions


def create_inbound_sms(
    service,
    notify_number=None,
    user_number="12025550104",
    provider_date=None,
    provider_reference=None,
    content="Hello",
    provider="sns",
    created_at=None,
):
    if not service.inbound_number:
        create_inbound_number(
            # create random inbound number
            notify_number or "1" + str(random.randint(1001001000, 9999999999)),
            provider=provider,
            service_id=service.id,
        )

    inbound = InboundSms(
        service=service,
        created_at=created_at or utc_now(),
        notify_number=service.get_inbound_number(),
        user_number=user_number,
        provider_date=provider_date or utc_now(),
        provider_reference=provider_reference or "foo",
        content=content,
        provider=provider,
    )
    dao_create_inbound_sms(inbound)
    return inbound


def create_service_inbound_api(
    service,
    url="https://something.com",
    bearer_token="some_super_secret",
):
    service_inbound_api = ServiceInboundApi(
        service_id=service.id,
        url=url,
        bearer_token=bearer_token,
        updated_by_id=service.users[0].id,
    )
    save_service_inbound_api(service_inbound_api)
    return service_inbound_api


def create_service_callback_api(
    service,
    url="https://something.com",
    bearer_token="some_super_secret",
    callback_type=CallbackType.DELIVERY_STATUS,
):
    service_callback_api = ServiceCallbackApi(
        service_id=service.id,
        url=url,
        bearer_token=bearer_token,
        updated_by_id=service.users[0].id,
        callback_type=callback_type,
    )
    save_service_callback_api(service_callback_api)
    return service_callback_api


def create_email_branding(
    id=None,
    colour="blue",
    logo="test_x2.png",
    name="test_org_1",
    text="DisplayName",
):
    data = {
        "colour": colour,
        "logo": logo,
        "name": name,
        "text": text,
    }
    if id:
        data["id"] = id
    email_branding = EmailBranding(**data)
    dao_create_email_branding(email_branding)

    return email_branding


def create_rate(start_date, value, notification_type):
    rate = Rate(
        id=uuid.uuid4(),
        valid_from=start_date,
        rate=value,
        notification_type=notification_type,
    )
    db.session.add(rate)
    db.session.commit()
    return rate


def create_api_key(service, key_type=KeyType.NORMAL, key_name=None):
    id_ = uuid.uuid4()

    name = key_name if key_name else f"{key_type} api key {id_}"

    api_key = ApiKey(
        service=service,
        name=name,
        created_by=service.created_by,
        key_type=key_type,
        id=id_,
        secret=uuid.uuid4(),
    )
    db.session.add(api_key)
    db.session.commit()
    return api_key


def create_inbound_number(number, provider="sns", active=True, service_id=None):
    inbound_number = InboundNumber(
        id=uuid.uuid4(),
        number=number,
        provider=provider,
        active=active,
        service_id=service_id,
    )
    db.session.add(inbound_number)
    db.session.commit()
    return inbound_number


def create_reply_to_email(service, email_address, is_default=True, archived=False):
    data = {
        "service": service,
        "email_address": email_address,
        "is_default": is_default,
        "archived": archived,
    }
    reply_to = ServiceEmailReplyTo(**data)

    db.session.add(reply_to)
    db.session.commit()

    return reply_to


def create_service_sms_sender(
    service, sms_sender, is_default=True, inbound_number_id=None, archived=False
):
    data = {
        "service_id": service.id,
        "sms_sender": sms_sender,
        "is_default": is_default,
        "inbound_number_id": inbound_number_id,
        "archived": archived,
    }
    service_sms_sender = ServiceSmsSender(**data)

    db.session.add(service_sms_sender)
    db.session.commit()

    return service_sms_sender


def create_annual_billing(service_id, free_sms_fragment_limit, financial_year_start):
    annual_billing = AnnualBilling(
        service_id=service_id,
        free_sms_fragment_limit=free_sms_fragment_limit,
        financial_year_start=financial_year_start,
    )
    db.session.add(annual_billing)
    db.session.commit()

    return annual_billing


def create_domain(domain, organization_id):
    domain = Domain(domain=domain, organization_id=organization_id)

    db.session.add(domain)
    db.session.commit()

    return domain


def create_organization(
    name="test_org_1",
    active=True,
    organization_type=None,
    domains=None,
    organization_id=None,
    purchase_order_number=None,
    billing_contact_names=None,
    billing_contact_email_addresses=None,
    billing_reference=None,
    email_branding_id=None,
):
    data = {
        "id": organization_id,
        "name": name,
        "active": active,
        "organization_type": organization_type,
        "purchase_order_number": purchase_order_number,
        "billing_contact_names": billing_contact_names,
        "billing_contact_email_addresses": billing_contact_email_addresses,
        "billing_reference": billing_reference,
        "email_branding_id": email_branding_id,
    }
    organization = Organization(**data)
    dao_create_organization(organization)

    for domain in domains or []:
        create_domain(domain, organization.id)

    return organization


def create_invited_org_user(
    organization,
    invited_by,
    email_address="invite@example.com",
):
    invited_org_user = InvitedOrganizationUser(
        email_address=email_address,
        invited_by=invited_by,
        organization=organization,
    )
    save_invited_org_user(invited_org_user)
    return invited_org_user


def create_ft_billing(
    local_date,
    template,
    *,
    provider="test",
    rate_multiplier=1,
    international=False,
    rate=0,
    billable_unit=1,
    notifications_sent=1,
):
    data = FactBilling(
        local_date=local_date,
        service_id=template.service_id,
        template_id=template.id,
        notification_type=template.template_type,
        provider=provider,
        rate_multiplier=rate_multiplier,
        international=international,
        rate=rate,
        billable_units=billable_unit,
        notifications_sent=notifications_sent,
    )
    db.session.add(data)
    db.session.commit()
    return data


def create_ft_notification_status(
    local_date,
    notification_type=NotificationType.SMS,
    service=None,
    template=None,
    job=None,
    key_type=KeyType.NORMAL,
    notification_status=NotificationStatus.DELIVERED,
    count=1,
):
    if job:
        template = job.template
    if template:
        service = template.service
        notification_type = template.template_type
    else:
        if not service:
            service = create_service()
        template = create_template(service=service, template_type=notification_type)

    data = FactNotificationStatus(
        local_date=local_date,
        template_id=template.id,
        service_id=service.id,
        job_id=job.id if job else uuid.UUID(int=0),
        notification_type=notification_type,
        key_type=key_type,
        notification_status=notification_status,
        notification_count=count,
    )
    db.session.add(data)
    db.session.commit()
    return data


def create_process_time(
    local_date="2021-03-01", messages_total=35, messages_within_10_secs=34
):
    data = FactProcessingTime(
        local_date=local_date,
        messages_total=messages_total,
        messages_within_10_secs=messages_within_10_secs,
    )
    fact_processing_time_dao.insert_update_processing_time(data)


def create_service_guest_list(service, email_address=None, mobile_number=None):
    if email_address:
        guest_list_user = ServiceGuestList.from_string(
            service.id, RecipientType.EMAIL, email_address
        )
    elif mobile_number:
        guest_list_user = ServiceGuestList.from_string(
            service.id, RecipientType.MOBILE, mobile_number
        )
    else:
        guest_list_user = ServiceGuestList.from_string(
            service.id, RecipientType.EMAIL, "guest_list_user@digital.fake.gov"
        )

    db.session.add(guest_list_user)
    db.session.commit()
    return guest_list_user


def create_complaint(service=None, notification=None, created_at=None):
    if not service:
        service = create_service()
    if not notification:
        template = create_template(service=service, template_type=TemplateType.EMAIL)
        notification = create_notification(template=template)

    complaint = Complaint(
        notification_id=notification.id,
        service_id=service.id,
        ses_feedback_id=str(uuid.uuid4()),
        complaint_type="abuse",
        complaint_date=utc_now(),
        created_at=created_at if created_at else datetime.now(),
    )
    db.session.add(complaint)
    db.session.commit()
    return complaint


def ses_complaint_callback_malformed_message_id():
    return {
        "Signature": "bb",
        "SignatureVersion": "1",
        "MessageAttributes": {},
        "MessageId": "98c6e927-af5d-5f3b-9522-bab736f2cbde",
        "UnsubscribeUrl": "https://sns.test-region.amazonaws.com",
        "TopicArn": "arn:ses_notifications",
        "Type": "Notification",
        "Timestamp": "2018-06-05T14:00:15.952Z",
        "Subject": None,
        "Message": '{"notificationType":"Complaint","complaint":{"complainedRecipients":[{"emailAddress":"recipient1@example.com"}],"timestamp":"2018-06-05T13:59:58.000Z","feedbackId":"ses_feedback_id"},"mail":{"timestamp":"2018-06-05T14:00:15.950Z","source":"\\"Some Service\\" <someservicenotifications.service.gov.uk>","sourceArn":"arn:identity/notifications.service.gov.uk","sourceIp":"52.208.24.161","sendingAccountId":"888450439860","badMessageId":"ref1","destination":["recipient1@example.com"]}}',  # noqa
        "SigningCertUrl": "https://sns.pem",
    }


def ses_complaint_callback_with_missing_complaint_type():
    """
    https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html#complaint-object
    """
    return {
        "Signature": "bb",
        "SignatureVersion": "1",
        "MessageAttributes": {},
        "MessageId": "98c6e927-af5d-5f3b-9522-bab736f2cbde",
        "UnsubscribeUrl": "https://sns.test-region.amazonaws.com",
        "TopicArn": "arn:ses_notifications",
        "Type": "Notification",
        "Timestamp": "2018-06-05T14:00:15.952Z",
        "Subject": None,
        "Message": '{"notificationType":"Complaint","complaint":{"complainedRecipients":[{"emailAddress":"recipient1@example.com"}],"timestamp":"2018-06-05T13:59:58.000Z","feedbackId":"ses_feedback_id"},"mail":{"timestamp":"2018-06-05T14:00:15.950Z","source":"\\"Some Service\\" <someservicenotifications.service.gov.uk>","sourceArn":"arn:identity/notifications.service.gov.uk","sourceIp":"52.208.24.161","sendingAccountId":"888450439860","messageId":"ref1","destination":["recipient1@example.com"]}}',  # noqa
        "SigningCertUrl": "https://sns.pem",
    }


def ses_complaint_callback():
    """
    https://docs.aws.amazon.com/ses/latest/DeveloperGuide/notification-contents.html#complaint-object
    """
    return {
        "Signature": "bb",
        "SignatureVersion": "1",
        "MessageAttributes": {},
        "MessageId": "98c6e927-af5d-5f3b-9522-bab736f2cbde",
        "UnsubscribeUrl": "https://sns.test-region.amazonaws.com",
        "TopicArn": "arn:ses_notifications",
        "Type": "Notification",
        "Timestamp": "2018-06-05T14:00:15.952Z",
        "Subject": None,
        "Message": '{"notificationType":"Complaint","complaint":{"complaintFeedbackType": "abuse", "complainedRecipients":[{"emailAddress":"recipient1@example.com"}],"timestamp":"2018-06-05T13:59:58.000Z","feedbackId":"ses_feedback_id"},"mail":{"timestamp":"2018-06-05T14:00:15.950Z","source":"\\"Some Service\\" <someservicenotifications.service.gov.uk>","sourceArn":"arn:identity/notifications.service.gov.uk","sourceIp":"52.208.24.161","sendingAccountId":"888450439860","messageId":"ref1","destination":["recipient1@example.com"]}}',  # noqa
        "SigningCertUrl": "https://sns.pem",
    }


def ses_notification_callback():
    return (
        '{\n  "Type" : "Notification",\n  "MessageId" : "ref1",'
        '\n  "TopicArn" : "arn:aws:sns:test-region:123456789012:testing",'
        '\n  "Message" : "{\\"notificationType\\":\\"Delivery\\",'
        '\\"mail\\":{\\"timestamp\\":\\"2016-03-14T12:35:25.909Z\\",'
        '\\"source\\":\\"test@test-domain.com\\",'
        '\\"sourceArn\\":\\"arn:aws:ses:test-region:123456789012:identity/testing-notify\\",'
        '\\"sendingAccountId\\":\\"123456789012\\",'
        '\\"messageId\\":\\"ref1\\",'
        '\\"destination\\":[\\"testing@testing.gov\\"]},'
        '\\"delivery\\":{\\"timestamp\\":\\"2016-03-14T12:35:26.567Z\\",'
        '\\"processingTimeMillis\\":658,'
        '\\"recipients\\":[\\"testing@testing.gov\\"],'
        '\\"smtpResponse\\":\\"250 2.0.0 OK 1457958926 uo5si26480932wjc.221 - gsmtp\\",'
        '\\"reportingMTA\\":\\"a6-238.smtp-out.test-region.amazonses.com\\"}}",'
        '\n  "Timestamp" : "2016-03-14T12:35:26.665Z",\n  "SignatureVersion" : "1",'
        '\n  "Signature" : "asdfasdfhsdhfkljashdfklashdfklhaskldfjh",'
        '\n  "SigningCertURL" : "https://sns.test-region.amazonaws.com/",'
        '\n  "UnsubscribeURL" : "https://sns.test-region.amazonaws.com/"\n}'
    )


def create_service_data_retention(
    service, notification_type=NotificationType.SMS, days_of_retention=3
):
    data_retention = insert_service_data_retention(
        service_id=service.id,
        notification_type=notification_type,
        days_of_retention=days_of_retention,
    )
    return data_retention


def create_invited_user(service=None, to_email_address=None):
    if service is None:
        service = create_service()
    if to_email_address is None:
        to_email_address = "invited_user@digital.fake.gov"

    from_user = service.users[0]

    data = {
        "service": service,
        "email_address": to_email_address,
        "from_user": from_user,
        "permissions": "send_messages,manage_service,manage_api_keys",
        "folder_permissions": [str(uuid.uuid4()), str(uuid.uuid4())],
    }
    invited_user = InvitedUser(**data)
    save_invited_user(invited_user)
    return invited_user


def create_template_folder(service, name="foo", parent=None):
    tf = TemplateFolder(name=name, service=service, parent=parent)
    db.session.add(tf)
    db.session.commit()
    return tf


def set_up_usage_data(start_date):
    year = int(start_date.strftime("%Y"))
    one_week_earlier = start_date - timedelta(days=7)
    two_days_later = start_date + timedelta(days=2)
    one_week_later = start_date + timedelta(days=7)
    # one_month_later = start_date + timedelta(days=31)

    # service with sms and letters:
    service_1_sms_and_letter = create_service(
        service_name="a - with sms and letter",
        purchase_order_number="service purchase order number",
        billing_contact_names="service billing contact names",
        billing_contact_email_addresses="service@billing.contact email@addresses.gov.uk",
        billing_reference="service billing reference",
    )
    sms_template_1 = create_template(
        service=service_1_sms_and_letter, template_type=TemplateType.SMS
    )
    create_annual_billing(
        service_id=service_1_sms_and_letter.id,
        free_sms_fragment_limit=10,
        financial_year_start=year,
    )
    org_1 = create_organization(
        name=f"Org for {service_1_sms_and_letter.name}",
        purchase_order_number="org1 purchase order number",
        billing_contact_names="org1 billing contact names",
        billing_contact_email_addresses="org1@billing.contact email@addresses.gov.uk",
        billing_reference="org1 billing reference",
    )
    dao_add_service_to_organization(
        service=service_1_sms_and_letter, organization_id=org_1.id
    )

    create_ft_billing(
        local_date=one_week_earlier,
        template=sms_template_1,
        billable_unit=2,
        rate=0.11,
    )
    create_ft_billing(
        local_date=start_date,
        template=sms_template_1,
        billable_unit=2,
        rate=0.11,
    )
    create_ft_billing(
        local_date=two_days_later,
        template=sms_template_1,
        billable_unit=1,
        rate=0.11,
    )

    # service with emails only:
    service_with_emails = create_service(service_name="b - emails")
    email_template = create_template(
        service=service_with_emails, template_type=TemplateType.EMAIL
    )
    org_2 = create_organization(
        name=f"Org for {service_with_emails.name}",
    )
    dao_add_service_to_organization(
        service=service_with_emails, organization_id=org_2.id
    )
    create_annual_billing(
        service_id=service_with_emails.id,
        free_sms_fragment_limit=0,
        financial_year_start=year,
    )

    create_ft_billing(
        local_date=start_date, template=email_template, notifications_sent=10
    )

    # service with chargeable SMS, without an organization
    service_with_sms_without_org = create_service(
        service_name="b - chargeable sms",
        purchase_order_number="sms purchase order number",
        billing_contact_names="sms billing contact names",
        billing_contact_email_addresses="sms@billing.contact email@addresses.gov.uk",
        billing_reference="sms billing reference",
    )
    sms_template = create_template(
        service=service_with_sms_without_org, template_type=TemplateType.SMS
    )
    create_annual_billing(
        service_id=service_with_sms_without_org.id,
        free_sms_fragment_limit=10,
        financial_year_start=year,
    )
    create_ft_billing(
        local_date=one_week_earlier, template=sms_template, rate=0.11, billable_unit=12
    )
    create_ft_billing(local_date=two_days_later, template=sms_template, rate=0.11)
    create_ft_billing(
        local_date=one_week_later, template=sms_template, billable_unit=2, rate=0.11
    )

    # service with SMS within free allowance
    service_with_sms_within_allowance = create_service(
        service_name="e - sms within allowance"
    )
    sms_template_2 = create_template(
        service=service_with_sms_within_allowance, template_type=TemplateType.SMS
    )
    create_annual_billing(
        service_id=service_with_sms_within_allowance.id,
        free_sms_fragment_limit=10,
        financial_year_start=year,
    )
    create_ft_billing(
        local_date=one_week_later, template=sms_template_2, billable_unit=2, rate=0.11
    )

    # service without ft_billing this year
    service_with_out_ft_billing_this_year = create_service(
        service_name="f - without ft_billing",
        purchase_order_number="sms purchase order number",
        billing_contact_names="sms billing contact names",
        billing_contact_email_addresses="sms@billing.contact email@addresses.gov.uk",
        billing_reference="sms billing reference",
    )
    create_annual_billing(
        service_id=service_with_out_ft_billing_this_year.id,
        free_sms_fragment_limit=10,
        financial_year_start=year,
    )
    dao_add_service_to_organization(
        service=service_with_out_ft_billing_this_year, organization_id=org_1.id
    )

    # dictionary with services and orgs to return
    return {
        "org_1": org_1,
        "service_1_sms_and_letter": service_1_sms_and_letter,
        "org_2": org_2,
        "service_with_emails": service_with_emails,
        "service_with_sms_without_org": service_with_sms_without_org,
        "service_with_sms_within_allowance": service_with_sms_within_allowance,
        "service_with_out_ft_billing_this_year": service_with_out_ft_billing_this_year,
    }


def create_webauthn_credential(
    user,
    name="my key",
    *,
    credential_data="ABC123",
    registration_response="DEF456",
):
    webauthn_credential = WebauthnCredential(
        user=user,
        name=name,
        credential_data=credential_data,
        registration_response=registration_response,
    )

    db.session.add(webauthn_credential)
    db.session.commit()
    return webauthn_credential
