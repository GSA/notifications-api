from enum import StrEnum


class TemplateType(StrEnum):
    SMS = "sms"
    EMAIL = "email"
    LETTER = "letter"


class NotificationType(StrEnum):
    SMS = "sms"
    EMAIL = "email"
    LETTER = "letter"


class TemplateProcessType(StrEnum):
    # TODO: Should Template.process_type be changed to use this?
    NORMAL = "normal"
    PRIORITY = "priority"


class AuthType(StrEnum):
    SMS = "sms_auth"
    EMAIL = "email_auth"
    WEBAUTHN = "webauthn_auth"


class UserState(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class CallbackType(StrEnum):
    DELIVERY_STATUS = "delivery_status"
    COMPLAINT = "complaint"


class OrganizationType(StrEnum):
    FEDERAL = "federal"
    STATE = "state"
    OTHER = "other"


class NotificationStatus(StrEnum):
    CANCELLED = "cancelled"
    CREATED = "created"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    PENDING = "pending"
    FAILED = "failed"
    TECHNICAL_FAILURE = "technical-failure"
    TEMPORARY_FAILURE = "temporary-failure"
    PERMANENT_FAILURE = "permanent-failure"
    PENDING_VIRUS_CHECK = "pending-virus-check"
    VALIDATION_FAILED = "validation-failed"
    VIRUS_SCAN_FAILED = "virus-scan-failed"

    @classmethod
    def failed_types(cls) -> tuple[str, ...]:
        return (
            cls.TECHNICAL_FAILURE,
            cls.TEMPORARY_FAILURE,
            cls.PERMANENT_FAILURE,
            cls.VALIDATION_FAILED,
            cls.VIRUS_SCAN_FAILED,
        )

    @classmethod
    def completed_types(cls) -> tuple[str, ...]:
        return (
            cls.SENT,
            cls.DELIVERED,
            cls.FAILED,
            cls.TECHNICAL_FAILURE,
            cls.TEMPORARY_FAILURE,
            cls.PERMANENT_FAILURE,
            cls.CANCELLED,
        )

    @classmethod
    def success_types(cls) -> tuple[str, ...]:
        return (cls.SENT, cls.DELIVERED)

    @classmethod
    def billable_types(cls) -> tuple[str, ...]:
        return (
            cls.SENDING,
            cls.SENT,
            cls.DELIVERED,
            cls.PENDING,
            cls.FAILED,
            cls.TEMPORARY_FAILURE,
            cls.PERMANENT_FAILURE,
        )

    @classmethod
    def billable_sms_types(cls) -> tuple[str, ...]:
        return (
            cls.SENDING,
            cls.SENT,  # internationally
            cls.DELIVERED,
            cls.PENDING,
            cls.TEMPORARY_FAILURE,
            cls.PERMANENT_FAILURE,
        )

    @classmethod
    def sent_email_types(cls) -> tuple[str, ...]:
        return (
            cls.SENDING,
            cls.DELIVERED,
            cls.TEMPORARY_FAILURE,
            cls.PERMANENT_FAILURE,
        )

    @classmethod
    def non_billable_types(cls) -> tuple[str, ...]:
        return tuple(set(cls) - set(cls.billable_types()))


class PermissionType(StrEnum):
    MANAGE_USERS = "manage_users"
    MANAGE_TEMPLATES = "manage_templates"
    MANAGE_SETTINGS = "manage_settings"
    SEND_TEXTS = "send_texts"
    SEND_EMAILS = "send_emails"
    MANAGE_API_KEYS = "manage_api_keys"
    PLATFORM_ADMIN = "platform_admin"
    VIEW_ACTIVITY = "view_activity"

    @classmethod
    def defaults(cls) -> tuple[str, ...]:
        return (
            cls.MANAGE_USERS,
            cls.MANAGE_TEMPLATES,
            cls.MANAGE_SETTINGS,
            cls.SEND_TEXTS,
            cls.SEND_EMAILS,
            cls.MANAGE_API_KEYS,
            cls.VIEW_ACTIVITY,
        )


class ServicePermissionType(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    INTERNATIONAL_SMS = "international_sms"
    INBOUND_SMS = "inbound_sms"
    SCHEDULE_NOTIFICATIONS = "schedule_notifications"
    EMAIL_AUTH = "email_auth"
    UPLOAD_DOCUMENT = "upload_document"
    EDIT_FOLDER_PERMISSIONS = "edit_folder_permissions"

    @classmethod
    def defaults(cls) -> tuple[str, ...]:
        return (
            cls.SMS,
            cls.EMAIL,
            cls.INTERNATIONAL_SMS,
        )


class RecipientType(StrEnum):
    MOBILE = "mobile"
    EMAIL = "email"


class KeyType(StrEnum):
    NORMAL = "normal"
    TEAM = "team"
    TEST = "test"


class JobStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in progress"
    FINISHED = "finished"
    SENDING_LIMITS_EXCEEDED = "sending limits exceeded"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    READY_TO_SEND = "ready to send"
    SENT_TO_DVLA = "sent to dvla"
    ERROR = "error"


class InvitedUserStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class BrandType(StrEnum):
    ORG = "org"
    BOTH = "both"
    ORG_BANNER = "org_banner"


class CodeType(StrEnum):
    EMAIL = "email"
    SMS = "sms"


class AgreementType(StrEnum):
    MOU = "MOU"
    IAA = "IAA"


class AgreementStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"


class StatisticsType(StrEnum):
    REQUESTED = "requested"
    DELIVERED = "delivered"
    FAILURE = "failure"
    PENDING = "pending"
