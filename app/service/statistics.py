from collections import defaultdict
from datetime import datetime

from app.dao.date_util import get_months_for_financial_year
from app.enums import (
    KeyType,
    NotificationStatus,
    NotificationType,
    StatisticsType,
    TemplateType,
)


def format_statistics(statistics, total_notifications=None):
    # statistics come in a named tuple with uniqueness from 'notification_type', 'status' - however missing
    # statuses/notification types won't be represented and the status types need to be simplified/summed up
    # so we can return emails/sms * created, sent, and failed
    counts = create_zeroed_stats_dicts()
    for row in statistics:
        # any row could be null, if the service either has no notifications in the notifications table,
        # or no historical data in the ft_notification_status table.
        if row.notification_type:
            _update_statuses_from_row(
                counts[row.notification_type],
                row,
            )

    # Update pending count directly
    if NotificationType.SMS in counts and total_notifications is not None:
        sms_dict = counts[NotificationType.SMS]
        requested_count = sms_dict[StatisticsType.REQUESTED]
        delivered_count = sms_dict[StatisticsType.DELIVERED]
        failed_count = sms_dict[StatisticsType.FAILURE]
        pending_count = total_notifications - (
            requested_count + delivered_count + failed_count
        )
        sms_dict[StatisticsType.PENDING] = pending_count

    return counts


def format_admin_stats(statistics):
    counts = create_stats_dict()

    for row in statistics:
        if row.key_type == KeyType.TEST:
            counts[row.notification_type]["test-key"] += row.count
        else:
            counts[row.notification_type]["total"] += row.count
            if row.status in (
                NotificationStatus.TECHNICAL_FAILURE,
                NotificationStatus.PERMANENT_FAILURE,
                NotificationStatus.TEMPORARY_FAILURE,
                NotificationStatus.VIRUS_SCAN_FAILED,
            ):
                counts[row.notification_type]["failures"][row.status] += row.count

    return counts


def create_stats_dict():
    stats_dict = {}
    for template in (TemplateType.SMS, TemplateType.EMAIL):
        stats_dict[template] = {}

        for status in ("total", "test-key"):
            stats_dict[template][status] = 0

        stats_dict[template]["failures"] = {
            NotificationStatus.TECHNICAL_FAILURE: 0,
            NotificationStatus.PERMANENT_FAILURE: 0,
            NotificationStatus.TEMPORARY_FAILURE: 0,
            NotificationStatus.VIRUS_SCAN_FAILED: 0,
        }
    return stats_dict


def format_monthly_template_notification_stats(year, rows):
    stats = {
        datetime.strftime(date, "%Y-%m"): {}
        for date in [datetime(year, month, 1) for month in range(4, 13)]
        + [datetime(year + 1, month, 1) for month in range(1, 4)]
    }

    for row in rows:
        formatted_month = row.month.strftime("%Y-%m")
        if str(row.template_id) not in stats[formatted_month]:
            stats[formatted_month][str(row.template_id)] = {
                "name": row.name,
                "type": row.template_type,
                "counts": dict.fromkeys(list(NotificationStatus), 0),
            }
        stats[formatted_month][str(row.template_id)]["counts"][row.status] += row.count

    return stats


def create_zeroed_stats_dicts():
    return {
        template_type: {status: 0 for status in StatisticsType}
        for template_type in (TemplateType.SMS, TemplateType.EMAIL)
    }


def _update_statuses_from_row(update_dict, row):
    requested_count = 0
    delivered_count = 0
    failed_count = 0

    # Update requested count
    if row.status != NotificationStatus.CANCELLED:
        update_dict[StatisticsType.REQUESTED] += row.count
        requested_count += row.count

    # Update delivered count
    if row.status in (NotificationStatus.DELIVERED, NotificationStatus.SENT):
        update_dict[StatisticsType.DELIVERED] += row.count
        delivered_count += row.count

    # Update failure count
    if row.status in (
        NotificationStatus.FAILED,
        NotificationStatus.TECHNICAL_FAILURE,
        NotificationStatus.TEMPORARY_FAILURE,
        NotificationStatus.PERMANENT_FAILURE,
        NotificationStatus.VALIDATION_FAILED,
        NotificationStatus.VIRUS_SCAN_FAILED,
    ):
        update_dict[StatisticsType.FAILURE] += row.count
        failed_count += row.count


def create_empty_monthly_notification_status_stats_dict(year):
    utc_month_starts = get_months_for_financial_year(year)
    # nested dicts - data[month][template type][status] = count
    return {
        start.strftime("%Y-%m"): {
            template_type: defaultdict(int)
            for template_type in (TemplateType.SMS, TemplateType.EMAIL)
        }
        for start in utc_month_starts
    }


def add_monthly_notification_status_stats(data, stats):
    for row in stats:
        month = row.month.strftime("%Y-%m")
        data[month][row.notification_type][row.notification_status] += row.count
        data[month][row.notification_type][StatisticsType.REQUESTED] += row.count
    return data
