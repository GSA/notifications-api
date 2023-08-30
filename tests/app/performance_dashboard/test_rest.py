from datetime import date

from tests.app.db import (
    create_ft_notification_status,
    create_process_time,
    create_template,
)


def test_performance_dashboard(sample_service, admin_request):
    template_sms = create_template(
        service=sample_service, template_type="sms", template_name="a"
    )
    template_email = create_template(
        service=sample_service, template_type="email", template_name="b"
    )
    create_ft_notification_status(
        local_date=date(2021, 2, 28),
        service=template_email.service,
        template=template_email,
        count=10,
    )
    create_ft_notification_status(
        local_date=date(2021, 2, 28),
        service=template_sms.service,
        template=template_sms,
        count=5,
    )
    create_ft_notification_status(
        local_date=date(2021, 3, 1),
        service=template_email.service,
        template=template_email,
        count=15,
    )
    create_ft_notification_status(
        local_date=date(2021, 3, 1),
        service=template_sms.service,
        template=template_sms,
        count=20,
    )
    create_ft_notification_status(
        local_date=date(2021, 3, 2),
        service=template_email.service,
        template=template_email,
        count=25,
    )
    create_ft_notification_status(
        local_date=date(2021, 3, 2),
        service=template_sms.service,
        template=template_sms,
        count=30,
    )
    create_ft_notification_status(
        local_date=date(2021, 3, 3),
        service=template_email.service,
        template=template_email,
        count=45,
    )
    create_ft_notification_status(
        local_date=date(2021, 3, 3),
        service=template_sms.service,
        template=template_sms,
        count=35,
    )

    create_process_time(
        local_date="2021-02-28", messages_total=15, messages_within_10_secs=14
    )
    create_process_time(
        local_date="2021-03-01", messages_total=35, messages_within_10_secs=34
    )
    create_process_time(
        local_date="2021-03-02", messages_total=15, messages_within_10_secs=12
    )
    create_process_time(
        local_date="2021-03-03", messages_total=15, messages_within_10_secs=14
    )

    results = admin_request.get(
        endpoint="performance_dashboard.get_performance_dashboard",
        start_date="2021-03-01",
        end_date="2021-03-02",
    )

    assert results["total_notifications"] == 185
    assert results["email_notifications"] == 10 + 15 + 25 + 45
    assert results["sms_notifications"] == 5 + 20 + 30 + 35
    assert results["notifications_by_type"] == [
        {"date": "2021-03-01", "emails": 15, "sms": 20},
        {"date": "2021-03-02", "emails": 25, "sms": 30},
    ]
    assert results["processing_time"] == [
        {"date": "2021-03-01", "percentage_under_10_seconds": 97.14285714285714},
        {"date": "2021-03-02", "percentage_under_10_seconds": 80.0},
    ]
    assert results["live_service_count"] == 1
    assert results["services_using_notify"][0]["service_name"] == sample_service.name
    assert not results["services_using_notify"][0]["organization_name"]
