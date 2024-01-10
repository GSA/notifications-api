from enum import Enum


class TemplateType(Enum):
    SMS = "sms"
    EMAIL = "email"
    LETTER = "letter"


class NotificationType(Enum):
    SMS = "sms"
    EMAIL = "email"
    LETTER = "letter"


class UserAuthType(Enum):
    SMS = "sms_auth"
    EMAIL = "email_auth"
    WEBAUTHN = "webauthn_auth"


class ServiceCallbackType(Enum):
    # TODO: Should ServiceCallbackApi.callback_type be changed to use this?
    DELIVERY_STATUS = "delivery_status"
    COMPLAINT = "complaint"


class ServicePermissionType(Enum):
    EMAIL = "email"
    SMS = "sms"
    INTERNATIONAL_SMS = "international_sms"
    INBOUND_SMS = "inbound_sms"
    SCHEDULE_NOTIFICATIONS = "schedule_notifications"
    EMAIL_AUTH = "email_auth"
    UPLOAD_DOCUMENT = "upload_document"
    EDIT_FOLDER_PERMISSIONS = "edit_folder_permissions"


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


class AgreementType(Enum):
    MOU = "MOU"
    IAA = "IAA"


class AgreementStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
