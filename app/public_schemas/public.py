from datetime import timezone

from marshmallow import Schema, fields, pre_dump


class PublicTemplateSchema(Schema):
    id = fields.UUID(required=True)
    name = fields.String(required=True)
    template_type = fields.String(required=True)
    version = fields.Integer(required=True)


class PublicJobSchema(Schema):
    id = fields.UUID(required=True)
    original_file_name = fields.String(required=True)


class PublicNotificationSchema(Schema):
    id = fields.UUID(required=True)
    to = fields.String(required=True)
    job_row_number = fields.Integer(allow_none=True)
    template_version = fields.Integer(required=True)
    billable_units = fields.Integer(required=True)
    notification_type = fields.String(required=True)
    created_at = fields.String(required=True)
    sent_at = fields.String(allow_none=True)
    updated_at = fields.String(allow_none=True)
    sent_by = fields.String(allow_none=True)
    status = fields.String(required=True)
    reference = fields.String(allow_none=True)
    template = fields.Nested(PublicTemplateSchema, required=True)
    service = fields.UUID(required=True)
    job = fields.Nested(PublicJobSchema, allow_none=True)
    api_key = fields.UUID(allow_none=True)
    body = fields.String(required=True)
    content_char_count = fields.Integer(required=True)

    @pre_dump
    def transform(self, notification, **kwargs):
        def to_rfc3339(dt):
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")

        return {
            **notification.__dict__,
            "created_at": to_rfc3339(getattr(notification, "created_at", None)),
            "sent_at": to_rfc3339(getattr(notification, "sent_at", None)),
            "updated_at": to_rfc3339(getattr(notification, "updated_at", None)),
            "sent_by": getattr(notification, "sent_by", None),
            "reference": getattr(notification, "reference", None),
            "service": str(notification.service.id) if notification.service else None,
            "api_key": str(notification.api_key.id) if notification.api_key else None,
            "body": getattr(notification, "body", None)
            or (notification.template.content if notification.template else ""),
            "content_char_count": len(
                getattr(notification, "body", "")
                or (notification.template.content if notification.template else "")
            ),
            "job": (
                {
                    "id": str(notification.job.id),
                    "original_file_name": notification.job.original_file_name,
                }
                if hasattr(notification, "job") and notification.job
                else None
            ),
        }
