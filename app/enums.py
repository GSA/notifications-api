from enum import Enum


class TemplateType(Enum):
    SMS = "sms"
    EMAIL = "email"
    LETTER = "letter"


class NotificationType(Enum):
    SMS = "sms"
    EMAIL = "email"
    LETTER = "letter"


class TemplateProcessType(Enum):
    # TODO: Should Template.process_type be changed to use this?
    NORMAL = "normal"
    PRIORITY = "priority"


class UserAuthType(Enum):
    SMS = "sms_auth"
    EMAIL = "email_auth"
    WEBAUTHN = "webauthn_auth"


class ServiceCallbackType(Enum):
    DELIVERY_STATUS = "delivery_status"
    COMPLAINT = "complaint"


class PermissionType(Enum):
    MANAGE_USERS = "manage_users"
    MANAGE_TEMPLATES = "manage_templates"
    MANAGE_SETTINGS = "manage_settings"
    SEND_TEXTS = "send_texts"
    SEND_EMAILS = "send_emails"
    MANAGE_API_KEYS = "manage_api_keys"
    PLATFORM_ADMIN = "platform_admin"
    VIEW_ACTIVITY = "view_activity"

    @property
    def defaults(self) -> tuple["PermissionType", ...]:
        cls = type(self)
        return (
            cls.MANAGE_USERS,
            cls.MANAGE_TEMPLATES,
            cls.MANAGE_SETTINGS,
            cls.SEND_TEXTS,
            cls.SEND_EMAILS,
            cls.MANAGE_API_KEYS,
            cls.VIEW_ACTIVITY,
        )

class ServicePermissionType(Enum):
    EMAIL = "email"
    SMS = "sms"
    INTERNATIONAL_SMS = "international_sms"
    INBOUND_SMS = "inbound_sms"
    SCHEDULE_NOTIFICATIONS = "schedule_notifications"
    EMAIL_AUTH = "email_auth"
    UPLOAD_DOCUMENT = "upload_document"
    EDIT_FOLDER_PERMISSIONS = "edit_folder_permissions"

    @property
    def defaults(self) -> tuple["ServicePermissionType", ...]:
        cls = type(self)
        return (
            cls.SMS,
            cls.EMAIL,
            cls.INTERNATIONAL_SMS,
        )

class GuestListRecipientType(Enum):
    MOBILE = "mobile"
    EMAIL = "email"


class KeyType(Enum):
    NORMAL = "normal"
    TEAM = "team"
    TEST = "test"


class JobStatusType(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in progress"
    FINISHED = "finished"
    SENDING_LIMITS_EXCEEDED = "sending limits exceeded"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    READY_TO_SEND = "ready to send"
    SENT_TO_DVLA = "sent to dvla"
    ERROR = "error"


class InvitedUserStatusType(Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class BrandingType(Enum):
    # TODO: Should EmailBranding.branding_type be changed to use this?
    GOVUK = "govuk"  # Deprecated outside migrations
    ORG = "org"
    BOTH = "both"
    ORG_BANNER = "org_banner"


class VerifyCodeType(Enum):
    EMAIL = "email"
    SMS = "sms"


class AgreementType(Enum):
    MOU = "MOU"
    IAA = "IAA"


class AgreementStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
