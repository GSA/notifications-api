from app import performance_platform_client
from app.dao.fact_notification_status_dao import (
    get_total_sent_notifications_for_day_and_type,
)
from app.models import NotificationType


# TODO: is this obsolete? it doesn't seem to be used anywhere
def send_total_notifications_sent_for_day_stats(start_time, notification_type, count):
    payload = performance_platform_client.format_payload(
        dataset="notifications",
        start_time=start_time,
        group_name="channel",
        group_value=notification_type,
        count=count,
    )

    performance_platform_client.send_stats_to_performance_platform(payload)


# TODO: is this obsolete? it doesn't seem to be used anywhere
def get_total_sent_notifications_for_day(day):
    email_count = get_total_sent_notifications_for_day_and_type(day, NotificationType.EMAIL)
    sms_count = get_total_sent_notifications_for_day_and_type(day, NotificationType.SMS)

    return {
        "email": email_count,
        "sms": sms_count,
    }
