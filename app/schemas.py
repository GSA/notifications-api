from datetime import timedelta
from uuid import UUID

from dateutil.parser import parse
from flask import current_app
from marshmallow import (
    EXCLUDE,
    Schema,
    ValidationError,
    fields,
    post_dump,
    post_load,
    pre_dump,
    pre_load,
    validates,
    validates_schema,
)
from marshmallow_enum import EnumField as BaseEnumField
from marshmallow_sqlalchemy import SQLAlchemyAutoSchema, auto_field, field_for

from app import models
from app.dao.permissions_dao import permission_dao
from app.enums import (
    NotificationStatus,
    OrganizationType,
    ServicePermissionType,
    TemplateProcessType,
    TemplateType,
)
from app.models import ServicePermission
from app.utils import DATETIME_FORMAT_NO_TIMEZONE, utc_now
from notifications_utils.recipients import (
    InvalidEmailError,
    InvalidPhoneError,
    validate_and_format_phone_number,
    validate_email_address,
    validate_phone_number,
)


class SafeEnumField(BaseEnumField):
    def fail(self, key, **kwargs):
        kwargs["values"] = ", ".join([str(mem.value) for mem in self.enum])
        kwargs["names"] = ", ".join([mem.name for mem in self.enum])
        msg = self.error or self.default_error_messages.get(key, "Invalid input")
        raise ValidationError(msg.format(**kwargs))


def _validate_positive_number(value, msg="Not a positive integer"):
    try:
        page_int = int(value)
    except ValueError:
        raise ValidationError(msg)
    if page_int < 1:
        raise ValidationError(msg)


def _validate_datetime_not_more_than_96_hours_in_future(
    dte, msg="Date cannot be more than 96hrs in the future"
):
    if dte > utc_now() + timedelta(hours=96):
        raise ValidationError(msg)


def _validate_datetime_not_in_past(dte, msg="Date cannot be in the past"):
    if dte < utc_now():
        raise ValidationError(msg)


class FlexibleDateTime(fields.DateTime):
    """
    Allows input data to not contain tz info.
    Outputs data using the output format that marshmallow version 2 used to use, OLD_MARSHMALLOW_FORMAT
    """

    DEFAULT_FORMAT = "flexible"
    OLD_MARSHMALLOW_FORMAT = "%Y-%m-%dT%H:%M:%S+00:00"

    def __init__(self, *args, allow_none=True, **kwargs):
        super().__init__(*args, allow_none=allow_none, **kwargs)
        self.DESERIALIZATION_FUNCS["flexible"] = parse
        self.SERIALIZATION_FUNCS["flexible"] = lambda x: x.strftime(
            self.OLD_MARSHMALLOW_FORMAT
        )


class UUIDsAsStringsMixin:
    @post_dump()
    def __post_dump(self, data, **kwargs):
        for key, value in data.items():
            if isinstance(value, UUID):
                data[key] = str(value)

            if isinstance(value, list):
                data[key] = [
                    (str(item) if isinstance(item, UUID) else item) for item in value
                ]
        return data


class BaseSchema(SQLAlchemyAutoSchema):
    class Meta:
        load_instance = True
        include_relationships = True
        unknown = EXCLUDE

    def __init__(self, load_json=False, *args, **kwargs):
        self.load_json = load_json
        super(BaseSchema, self).__init__(*args, **kwargs)

    @post_load
    def make_instance(self, data, **kwargs):
        """Deserialize data to an instance of the model. Update an existing row
        if specified in `self.instance` or loaded by primary key(s) in the data;
        else create a new row.
        :param data: Data to deserialize.
        """
        if self.load_json:
            return data
        return super(BaseSchema, self).make_instance(data)


class UserSchema(BaseSchema):
    permissions = fields.Method("user_permissions", dump_only=True)
    password_changed_at = field_for(
        models.User, "password_changed_at", format=DATETIME_FORMAT_NO_TIMEZONE
    )
    created_at = field_for(
        models.User, "created_at", format=DATETIME_FORMAT_NO_TIMEZONE
    )
    updated_at = FlexibleDateTime()
    logged_in_at = FlexibleDateTime()
    auth_type = auto_field(by_value=True)
    password = fields.String(required=True, load_only=True)

    def user_permissions(self, usr):
        retval = {}
        for x in permission_dao.get_permissions_by_user_id(usr.id):
            service_id = str(x.service_id)
            if service_id not in retval:
                retval[service_id] = []
            retval[service_id].append(x.permission)
        return retval

    class Meta(BaseSchema.Meta):
        model = models.User
        exclude = (
            "_password",
            "created_at",
            "email_access_validated_at",
            "updated_at",
            "verify_codes",
        )

    @validates("name")
    def validate_name(self, value, data_key):
        if not value:
            current_app.logger.exception(f"{data_key}: Invalid name")
            raise ValidationError("Invalid name")

    @validates("email_address")
    def validate_email_address(self, value, data_key):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            current_app.logger.exception(f"{data_key}: {str(e)}")
            raise ValidationError(str(e))

    @validates("mobile_number")
    def validate_mobile_number(self, value, data_key):
        try:
            if value is not None:
                validate_phone_number(value, international=True)
        except InvalidPhoneError as error:
            current_app.logger.exception(f"{data_key}: {str(error)}")
            raise ValidationError(f"Invalid phone number: {str(error)}")


class UserUpdateAttributeSchema(BaseSchema):
    auth_type = auto_field(by_value=True)
    email_access_validated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.User
        exclude = (
            "_password",
            "created_at",
            "failed_login_count",
            "id",
            "logged_in_at",
            "password_changed_at",
            "platform_admin",
            "state",
            "updated_at",
            "verify_codes",
        )

    @validates("name")
    def validate_name(self, value, data_key):
        if not value:
            current_app.logger.exception(f"{data_key}: Invalid name")
            raise ValidationError("Invalid name")

    @validates("email_address")
    def validate_email_address(self, value, data_key):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            current_app.logger.exception(f"{data_key}: {str(e)}")
            raise ValidationError(str(e))

    @validates("mobile_number")
    def validate_mobile_number(self, value, data_key):
        try:
            if value is not None:
                validate_phone_number(value, international=True)
        except InvalidPhoneError as error:
            current_app.logger.exception(
                f"{data_key}: Invalid phone number ({str(error)})"
            )
            raise ValidationError(f"Invalid phone number: {str(error)}")

    @validates_schema(pass_original=True)
    def check_unknown_fields(self, data, original_data, **kwargs):
        for key in original_data:
            if key not in self.fields:
                raise ValidationError(f"Unknown field name {key}")


class UserUpdatePasswordSchema(BaseSchema):
    class Meta(BaseSchema.Meta):
        model = models.User

    @validates_schema(pass_original=True)
    def check_unknown_fields(self, data, original_data, **kwargs):
        for key in original_data:
            if key not in self.fields:
                raise ValidationError(f"Unknown field name {key}")


class ProviderDetailsSchema(BaseSchema):
    created_by = fields.Nested(
        UserSchema, only=["id", "name", "email_address"], dump_only=True
    )
    updated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.ProviderDetails


class ProviderDetailsHistorySchema(BaseSchema):
    created_by = fields.Nested(
        UserSchema, only=["id", "name", "email_address"], dump_only=True
    )
    updated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.ProviderDetailsHistory


class ServiceSchema(BaseSchema, UUIDsAsStringsMixin):
    created_by = field_for(models.Service, "created_by", required=True)
    organization_type = SafeEnumField(
        OrganizationType, by_value=True, required=False, allow_none=True
    )

    permissions = fields.Method(
        "serialize_service_permissions", "deserialize_service_permissions"
    )
    email_branding = field_for(models.Service, "email_branding")
    organization = field_for(models.Service, "organization")
    go_live_at = field_for(
        models.Service, "go_live_at", format=DATETIME_FORMAT_NO_TIMEZONE
    )

    def serialize_service_permissions(self, service):
        return [p.permission for p in service.permissions]

    def deserialize_service_permissions(self, in_data):
        if isinstance(in_data, dict) and "permissions" in in_data:
            str_permissions = in_data["permissions"]
            permissions = []
            for p in str_permissions:
                permission = ServicePermission(service_id=in_data["id"], permission=p)
                permissions.append(permission)

            in_data["permissions"] = permissions

        return in_data

    class Meta(BaseSchema.Meta):
        model = models.Service
        exclude = (
            "all_template_folders",
            "annual_billing",
            "api_keys",
            "complaints",
            "created_at",
            "data_retention",
            "guest_list",
            "inbound_number",
            "inbound_sms",
            "jobs",
            "reply_to_email_addresses",
            "service_sms_senders",
            "templates",
            "updated_at",
            "users",
            "version",
        )

    @validates("permissions")
    def validate_permissions(self, value, data_key):
        permissions = [v.permission for v in value]
        for p in permissions:
            if p not in {e for e in ServicePermissionType}:
                current_app.logger.exception(
                    f"{data_key}: Invalid Service Permission: '{p}'"
                )
                raise ValidationError(f"Invalid Service Permission: '{p}'")

        if len(set(permissions)) != len(permissions):
            duplicates = list(set([x for x in permissions if permissions.count(x) > 1]))
            current_app.logger.exception(
                f"{data_key}: Duplicate Service Permission: {duplicates}"
            )
            raise ValidationError(f"Duplicate Service Permission: {duplicates}")

    @pre_load()
    def format_for_data_model(self, in_data, **kwargs):
        if isinstance(in_data, dict) and "permissions" in in_data:
            str_permissions = in_data["permissions"]
            permissions = []
            for p in str_permissions:
                permission = ServicePermission(service_id=in_data["id"], permission=p)
                permissions.append(permission)

            in_data["permissions"] = permissions

        return in_data


class TemplateTypeFieldOnlySchema(Schema):
    template_type = fields.String(required=True)


class NotificationStatusFieldOnlySchema(Schema):
    status = fields.String(required=True)


class DetailedServiceSchema(BaseSchema):
    statistics = fields.Dict()
    organization_type = field_for(models.Service, "organization_type")
    go_live_at = FlexibleDateTime()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.Service
        exclude = (
            "all_template_folders",
            "annual_billing",
            "api_keys",
            "created_by",
            "email_branding",
            "email_from",
            "guest_list",
            "inbound_api",
            "inbound_number",
            "inbound_sms",
            "jobs",
            "message_limit",
            "total_message_limit",
            "permissions",
            "rate_limit",
            "reply_to_email_addresses",
            "service_sms_senders",
            "templates",
            "users",
            "version",
        )


class NotificationModelSchema(BaseSchema):
    class Meta(BaseSchema.Meta):
        model = models.Notification
        exclude = (
            "_personalisation",
            "job",
            "service",
            "template",
            "api_key",
        )

    status = auto_field(by_value=True)
    created_at = FlexibleDateTime()
    sent_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()


class BaseTemplateSchema(BaseSchema):
    reply_to = fields.Method("get_reply_to", allow_none=True)
    reply_to_text = fields.Method("get_reply_to_text", allow_none=True)
    template_type = auto_field(by_value=True)

    def get_reply_to(self, template):
        return template.reply_to

    def get_reply_to_text(self, template):
        return template.get_reply_to_text()

    class Meta(BaseSchema.Meta):
        model = models.Template
        exclude = ("service_id", "jobs")


class TemplateSchema(BaseTemplateSchema, UUIDsAsStringsMixin):
    created_by = field_for(models.Template, "created_by", required=True)
    process_type = auto_field(by_value=True)
    redact_personalisation = fields.Method("redact")
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()

    def redact(self, template):
        return template.redact_personalisation

    @validates_schema
    def validate_type(self, data, **kwargs):
        if data.get("template_type") == TemplateType.EMAIL:
            subject = data.get("subject")
            if not subject or subject.strip() == "":
                raise ValidationError("Invalid template subject", "subject")


class TemplateSchemaNoDetail(TemplateSchema):
    class Meta(TemplateSchema.Meta):
        exclude = TemplateSchema.Meta.exclude + (
            "archived",
            "created_at",
            "created_by",
            "created_by_id",
            "hidden",
            "process_type",
            "redact_personalisation",
            "reply_to",
            "reply_to_text",
            "service",
            "subject",
            "template_redacted",
            "updated_at",
            "version",
        )

    @pre_dump
    def remove_content_for_non_broadcast_templates(self, template, **kwargs):
        template.content = None

        return template


class TemplateHistorySchema(BaseSchema):
    reply_to = fields.Method("get_reply_to", allow_none=True)
    reply_to_text = fields.Method("get_reply_to_text", allow_none=True)
    process_type = SafeEnumField(TemplateProcessType, by_value=True)
    template_type = auto_field(by_value=True)

    created_by = fields.Nested(
        UserSchema, only=["id", "name", "email_address"], dump_only=True
    )
    created_at = field_for(
        models.Template, "created_at", format=DATETIME_FORMAT_NO_TIMEZONE
    )
    updated_at = FlexibleDateTime()

    def get_reply_to(self, template):
        return template.reply_to

    def get_reply_to_text(self, template):
        return template.get_reply_to_text()

    class Meta(BaseSchema.Meta):
        model = models.TemplateHistory


class ApiKeySchema(BaseSchema):
    created_by = field_for(models.ApiKey, "created_by", required=True)
    key_type = auto_field(by_value=True)
    expiry_date = FlexibleDateTime()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.ApiKey
        exclude = ("service", "_secret")


class JobSchema(BaseSchema):
    created_by_user = fields.Nested(
        UserSchema,
        attribute="created_by",
        data_key="created_by",
        only=["id", "name"],
        dump_only=True,
    )
    created_by = field_for(models.Job, "created_by", required=True, load_only=True)
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()
    processing_started = FlexibleDateTime()
    processing_finished = FlexibleDateTime()

    job_status = auto_field(by_value=True)

    scheduled_for = FlexibleDateTime()
    service_name = fields.Nested(
        ServiceSchema,
        attribute="service",
        data_key="service_name",
        only=["name"],
        dump_only=True,
    )

    template_name = fields.Method("get_template_name", dump_only=True)
    template_type = fields.Method("get_template_type", dump_only=True)

    def get_template_name(self, job):
        return job.template.name

    def get_template_type(self, job):
        return job.template.template_type.value

    @validates("scheduled_for")
    def validate_scheduled_for(self, value, data_key):
        _validate_datetime_not_in_past(value)
        _validate_datetime_not_more_than_96_hours_in_future(value)

    class Meta(BaseSchema.Meta):
        model = models.Job
        exclude = (
            "notifications",
            "notifications_delivered",
            "notifications_failed",
            "notifications_sent",
        )


class NotificationSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    status = fields.Enum(NotificationStatus, by_value=True, required=False)
    personalisation = fields.Dict(required=False)


class SmsNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)

    @validates("to")
    def validate_to(self, value, data_key):
        try:
            validate_phone_number(value, international=True)
        except InvalidPhoneError as error:
            current_app.logger.exception(
                f"{data_key}: Invalid phone number ({str(error)}"
            )
            raise ValidationError(f"Invalid phone number: {str(error)}")

    @post_load
    def format_phone_number(self, item, **kwargs):
        item["to"] = validate_and_format_phone_number(item["to"], international=True)
        return item


class EmailNotificationSchema(NotificationSchema):
    to = fields.Str(required=True)
    template = fields.Str(required=True)

    @validates("to")
    def validate_to(self, value, data_key):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            current_app.logger.exception(f"{data_key}: {str(e)}")
            raise ValidationError(str(e))


class SmsTemplateNotificationSchema(SmsNotificationSchema):
    template = fields.Str(required=True)
    job = fields.String()


class NotificationWithTemplateSchema(BaseSchema):
    class Meta(BaseSchema.Meta):
        unknown = EXCLUDE
        model = models.Notification
        exclude = ("_personalisation",)

    template = fields.Nested(
        TemplateSchema,
        only=[
            "id",
            "version",
            "name",
            "template_type",
            "content",
            "subject",
            "redact_personalisation",
        ],
        dump_only=True,
    )
    template_version = fields.Integer()
    job = fields.Nested(JobSchema, only=["id", "original_file_name"], dump_only=True)
    created_by = fields.Nested(
        UserSchema, only=["id", "name", "email_address"], dump_only=True
    )
    status = auto_field(by_value=True)
    personalisation = fields.Dict(required=False)
    notification_type = auto_field(by_value=True)
    key_type = auto_field(by_value=True)
    key_name = fields.String()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()
    sent_at = FlexibleDateTime()

    @pre_dump
    def add_api_key_name(self, in_data, **kwargs):
        if in_data.api_key:
            in_data.key_name = in_data.api_key.name
        else:
            in_data.key_name = None
        return in_data


class InvitedUserSchema(BaseSchema):
    auth_type = auto_field(by_value=True)
    created_at = FlexibleDateTime()
    status = auto_field(by_value=True)

    class Meta(BaseSchema.Meta):
        model = models.InvitedUser

    @validates("email_address")
    def validate_to(self, value, data_key):
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            current_app.logger.exception(f"{data_key}: {str(e)}")
            raise ValidationError(str(e))


class EmailDataSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    email = fields.Str(required=True)
    next = fields.Str(required=False)
    admin_base_url = fields.Str(required=False)

    def __init__(self, partial_email=False):
        super().__init__()
        self.partial_email = partial_email

    @validates("email")
    def validate_email(self, value, data_key):
        if self.partial_email:
            return
        try:
            validate_email_address(value)
        except InvalidEmailError as e:
            current_app.logger.exception(f"{data_key}: {str(e)}")
            raise ValidationError(str(e))


class NotificationsFilterSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    template_type = fields.Nested(TemplateTypeFieldOnlySchema, many=True)
    status = fields.Nested(NotificationStatusFieldOnlySchema, many=True)
    page = fields.Int(required=False)
    page_size = fields.Int(required=False)
    limit_days = fields.Int(required=False)
    include_jobs = fields.Boolean(required=False)
    include_from_test_key = fields.Boolean(required=False)
    older_than = fields.UUID(required=False)
    format_for_csv = fields.Boolean()
    to = fields.String()
    include_one_off = fields.Boolean(required=False)
    count_pages = fields.Boolean(required=False)

    @pre_load
    def handle_multidict(self, in_data, **kwargs):
        out_data = dict(in_data)

        if isinstance(in_data, dict) and hasattr(in_data, "getlist"):
            if "template_type" in in_data:
                out_data["template_type"] = [
                    {"template_type": x} for x in in_data.getlist("template_type")
                ]
            if "status" in in_data:
                out_data["status"] = [{"status": x} for x in in_data.getlist("status")]

        return out_data

    @post_load
    def convert_schema_object_to_field(self, in_data, **kwargs):
        if "template_type" in in_data:
            in_data["template_type"] = [
                x["template_type"] for x in in_data["template_type"]
            ]
        if "status" in in_data:
            in_data["status"] = [x["status"] for x in in_data["status"]]
        return in_data

    @validates("page")
    def validate_page(self, value, data_key):
        _validate_positive_number(value)

    @validates("page_size")
    def validate_page_size(self, value, data_key):
        _validate_positive_number(value)


class ServiceHistorySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.UUID()
    name = fields.String()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()
    active = fields.Boolean()
    message_limit = fields.Integer()
    total_message_limit = fields.Integer()
    restricted = fields.Boolean()
    email_from = fields.String()
    created_by_id = fields.UUID()
    version = fields.Integer()


class ApiKeyHistorySchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.UUID()
    name = fields.String()
    service_id = fields.UUID()
    expiry_date = FlexibleDateTime()
    created_at = FlexibleDateTime()
    updated_at = FlexibleDateTime()
    created_by_id = fields.UUID()


class EventSchema(BaseSchema):
    created_at = FlexibleDateTime()

    class Meta(BaseSchema.Meta):
        model = models.Event


class UnarchivedTemplateSchema(BaseSchema):
    archived = fields.Boolean(required=True)

    @validates_schema
    def validate_archived(self, data, **kwargs):
        if data["archived"]:
            raise ValidationError("Template has been deleted", "template")


# should not be used on its own for dumping - only for loading
create_user_schema = UserSchema(transient=True)
user_update_schema_load_json = UserUpdateAttributeSchema(
    load_json=True, partial=True, transient=True
)
user_update_password_schema_load_json = UserUpdatePasswordSchema(
    only=("_password",), load_json=True, partial=True
)
service_schema = ServiceSchema()
detailed_service_schema = DetailedServiceSchema()
template_schema = TemplateSchema()
template_schema_no_detail = TemplateSchemaNoDetail()
api_key_schema = ApiKeySchema()
sms_template_notification_schema = SmsTemplateNotificationSchema()
email_notification_schema = EmailNotificationSchema()
notification_schema = NotificationModelSchema()
notification_with_template_schema = NotificationWithTemplateSchema()
invited_user_schema = InvitedUserSchema()
email_data_request_schema = EmailDataSchema()
partial_email_data_request_schema = EmailDataSchema(partial_email=True)
notifications_filter_schema = NotificationsFilterSchema()
public_notification_response_schema = NotificationWithTemplateSchema()
service_history_schema = ServiceHistorySchema()
api_key_history_schema = ApiKeyHistorySchema()
template_history_schema = TemplateHistorySchema()
event_schema = EventSchema()
provider_details_schema = ProviderDetailsSchema()
provider_details_history_schema = ProviderDetailsHistorySchema()
job_schema = JobSchema()
