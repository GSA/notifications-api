from datetime import datetime, timezone
from uuid import UUID

from marshmallow import EXCLUDE, Schema, fields, post_dump


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


class PublicNotificationResponseSchema(PublicNotificationSchema):
    class Meta:
        unknown = EXCLUDE

    @post_dump
    def transform(self, data, **kwargs):
        def to_rfc3339(dt):
            if dt is None:
                return None
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt)
                except ValueError:
                    return dt  # fallback, might already be valid
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat().replace("+00:00", "Z")

        data["created_at"] = to_rfc3339(data.get("created_at"))
        data["sent_at"] = to_rfc3339(data.get("sent_at"))
        data["updated_at"] = to_rfc3339(data.get("updated_at"))

        # Fallback content
        template = data.get("template", {})
        body = data.get("body") or (
            template.get("content") if isinstance(template, dict) else ""
        )
        data["body"] = body or ""
        data["content_char_count"] = len(data["body"])

        # Extract UUID string for service
        service = data.get("service")
        if hasattr(service, "id"):
            data["service"] = str(service.id)
        elif isinstance(service, UUID):
            data["service"] = str(service)
        elif isinstance(service, str) and service.startswith("<Service "):
            # fallback if __str__ was called on the SQLAlchemy object
            data["service"] = service.split("<Service ")[1].rstrip(">")
        else:
            data["service"] = str(service)  # best effort fallback

        # Extract UUID string for api_key
        api_key = data.get("api_key")
        if hasattr(api_key, "id"):
            data["api_key"] = str(api_key.id)
        elif isinstance(api_key, UUID):
            data["api_key"] = str(api_key)
        elif isinstance(api_key, str) and api_key.startswith("<ApiKey "):
            data["api_key"] = api_key.split("<ApiKey ")[1].rstrip(">")
        else:
            data["api_key"] = str(api_key) if api_key else None

        # Fix job dict
        job = data.get("job")
        if isinstance(job, dict) and "id" in job:
            job_id = job.get("id")
            job["id"] = str(job_id) if job_id else None
            data["job"] = job

        return data
