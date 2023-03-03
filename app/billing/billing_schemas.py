from datetime import datetime

create_or_update_free_sms_fragment_limit_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST annual billing schema",
    "type": "object",
    "title": "Create",
    "properties": {
        "free_sms_fragment_limit": {"type": "integer", "minimum": 0},
    },
    "required": ["free_sms_fragment_limit"]
}


def serialize_ft_billing_remove_emails(rows):
    return [
        {
            "month": (datetime.strftime(row.month, "%B")),
            "notification_type": row.notification_type,
            "chargeable_units": row.chargeable_units,
            "notifications_sent": row.notifications_sent,
            "rate": float(row.rate),
            "cost": float(row.cost),
            "free_allowance_used": row.free_allowance_used,
            "charged_units": row.charged_units,
        }
        for row in rows
        if row.notification_type != 'email'
    ]


def serialize_ft_billing_yearly_totals(rows):
    return [
        {
            "notification_type": row.notification_type,
            "chargeable_units": row.chargeable_units,
            "notifications_sent": row.notifications_sent,
            "rate": float(row.rate),
            "cost": float(row.cost),
            "free_allowance_used": row.free_allowance_used,
            "charged_units": row.charged_units,
        }
        for row in rows
    ]
