import itertools
import uuid

from flask import current_app, url_for
from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, JSONB, UUID
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import DeclarativeMeta, declared_attr
from sqlalchemy.orm import validates
from sqlalchemy.orm.collections import attribute_mapped_collection

from app import db, get_encryption
from app.enums import (
    AgreementStatus,
    AgreementType,
    AuthType,
    BrandType,
    CallbackType,
    CodeType,
    InvitedUserStatus,
    JobStatus,
    KeyType,
    NotificationStatus,
    NotificationType,
    OrganizationType,
    PermissionType,
    RecipientType,
    ServicePermissionType,
    TemplateProcessType,
    TemplateType,
    UserState,
)
from app.hashing import check_hash, hashpw
from app.history_meta import Versioned
from app.utils import (
    DATETIME_FORMAT,
    DATETIME_FORMAT_NO_TIMEZONE,
    get_dt_string_or_none,
    utc_now,
)
from notifications_utils.clients.encryption.encryption_client import EncryptionError
from notifications_utils.recipients import (
    InvalidEmailError,
    InvalidPhoneError,
    try_validate_and_format_phone_number,
    validate_email_address,
    validate_phone_number,
)
from notifications_utils.template import PlainTextEmailTemplate, SMSMessageTemplate

encryption = get_encryption()


def filter_null_value_fields(obj):
    return dict(filter(lambda x: x[1] is not None, obj.items()))


_enum_column_names = {
    AuthType: "auth_types",
    BrandType: "brand_types",
    OrganizationType: "organization_types",
    ServicePermissionType: "service_permission_types",
    RecipientType: "recipient_types",
    CallbackType: "callback_types",
    KeyType: "key_types",
    TemplateType: "template_types",
    TemplateProcessType: "template_process_types",
    NotificationType: "notification_types",
    JobStatus: "job_statuses",
    CodeType: "code_types",
    NotificationStatus: "notify_statuses",
    InvitedUserStatus: "invited_user_statuses",
    PermissionType: "permission_types",
    AgreementType: "agreement_types",
    AgreementStatus: "agreement_statuses",
    UserState: "user_states",
}


def enum_column(enum_type, **kwargs):
    return db.Column(
        db.Enum(
            enum_type,
            name=_enum_column_names[enum_type],
            values_callable=(lambda x: [i.value for i in x]),
        ),
        **kwargs,
    )


class HistoryModel:
    @classmethod
    def from_original(cls, original):
        history = cls()
        history.update_from_original(original)
        return history

    def update_from_original(self, original):
        for c in self.__table__.columns:
            # in some cases, columns may have different names to their underlying db column -  so only copy those
            # that we can, and leave it up to subclasses to deal with any oddities/properties etc.
            if hasattr(original, c.name):
                setattr(self, c.name, getattr(original, c.name))
            else:
                current_app.logger.debug(
                    "{} has no column {} to copy from".format(original, c.name)
                )


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String, nullable=False, index=True, unique=False)
    email_address = db.Column(db.String(255), nullable=False, index=True, unique=True)
    login_uuid = db.Column(db.Text, nullable=True, index=True, unique=True)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=utc_now,
    )
    _password = db.Column(db.String, index=False, unique=False, nullable=False)
    mobile_number = db.Column(db.String, index=False, unique=False, nullable=True)
    password_changed_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    logged_in_at = db.Column(db.DateTime, nullable=True)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    state = enum_column(
        UserState, index=True, nullable=False, default=UserState.PENDING
    )
    platform_admin = db.Column(db.Boolean, nullable=False, default=False)
    current_session_id = db.Column(UUID(as_uuid=True), nullable=True)
    auth_type = enum_column(AuthType, index=True, nullable=False, default=AuthType.SMS)
    email_access_validated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    preferred_timezone = db.Column(
        db.Text,
        nullable=True,
        index=False,
        unique=False,
        default="US/Eastern",
    )

    # either email auth or a mobile number must be provided
    CheckConstraint(
        "auth_type in (AuthType.EMAIL, AuthType.WEBAUTHN) or mobile_number is not null"
    )

    services = db.relationship("Service", secondary="user_to_service", backref="users")
    organizations = db.relationship(
        "Organization",
        secondary="user_to_organization",
        backref="users",
    )

    @validates("mobile_number")
    def validate_mobile_number(self, key, number):
        try:
            if number is not None:
                return validate_phone_number(number, international=True)
        except InvalidPhoneError as err:
            raise ValueError(str(err)) from err

    @property
    def password(self):
        raise AttributeError("Password not readable")

    @property
    def can_use_webauthn(self):
        if self.platform_admin:
            return True

        if self.auth_type == AuthType.WEBAUTHN:
            return True

        return any(
            str(service.id) == current_app.config["NOTIFY_SERVICE_ID"]
            for service in self.services
        )

    @password.setter
    def password(self, password):
        self._password = hashpw(password)

    def check_password(self, password):
        return check_hash(password, self._password)

    def get_permissions(self, service_id=None):
        from app.dao.permissions_dao import permission_dao

        if service_id:
            return [
                x.permission
                for x in permission_dao.get_permissions_by_user_id_and_service_id(
                    self.id, service_id
                )
            ]

        retval = {}
        for x in permission_dao.get_permissions_by_user_id(self.id):
            service_id = str(x.service_id)
            if service_id not in retval:
                retval[service_id] = []
            retval[service_id].append(x.permission)
        return retval

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "email_address": self.email_address,
            "login_uuid": self.login_uuid,
            "auth_type": self.auth_type,
            "current_session_id": self.current_session_id,
            "failed_login_count": self.failed_login_count,
            "email_access_validated_at": self.email_access_validated_at.strftime(
                DATETIME_FORMAT
            ),
            "logged_in_at": get_dt_string_or_none(self.logged_in_at),
            "mobile_number": self.mobile_number,
            "organizations": [x.id for x in self.organizations if x.active],
            "password_changed_at": self.password_changed_at.strftime(
                DATETIME_FORMAT_NO_TIMEZONE
            ),
            "permissions": self.get_permissions(),
            "platform_admin": self.platform_admin,
            "services": [x.id for x in self.services if x.active],
            "can_use_webauthn": self.can_use_webauthn,
            "state": self.state,
            "preferred_timezone": self.preferred_timezone,
        }

    def serialize_for_users_list(self):
        return {
            "id": self.id,
            "name": self.name,
            "email_address": self.email_address,
            "login_uuid": self.login_uuid,
            "mobile_number": self.mobile_number,
        }


class ServiceUser(db.Model):
    __tablename__ = "user_to_service"
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), primary_key=True)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        primary_key=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "service_id",
            name="uix_user_to_service",
        ),
    )


user_to_organization = db.Table(
    "user_to_organization",
    db.Model.metadata,
    db.Column("user_id", UUID(as_uuid=True), db.ForeignKey("users.id")),
    db.Column("organization_id", UUID(as_uuid=True), db.ForeignKey("organization.id")),
    UniqueConstraint("user_id", "organization_id", name="uix_user_to_organization"),
)


user_folder_permissions = db.Table(
    "user_folder_permissions",
    db.Model.metadata,
    db.Column("user_id", UUID(as_uuid=True), primary_key=True),
    db.Column(
        "template_folder_id",
        UUID(as_uuid=True),
        db.ForeignKey("template_folder.id"),
        primary_key=True,
    ),
    db.Column("service_id", UUID(as_uuid=True), primary_key=True),
    db.ForeignKeyConstraint(
        ["user_id", "service_id"],
        ["user_to_service.user_id", "user_to_service.service_id"],
    ),
    db.ForeignKeyConstraint(
        ["template_folder_id", "service_id"],
        ["template_folder.id", "template_folder.service_id"],
    ),
)


class EmailBranding(db.Model):
    __tablename__ = "email_branding"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    colour = db.Column(db.String(7), nullable=True)
    logo = db.Column(db.String(255), nullable=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    text = db.Column(db.String(255), nullable=True)
    brand_type = enum_column(
        BrandType,
        index=True,
        nullable=False,
        default=BrandType.ORG,
    )

    def serialize(self):
        serialized = {
            "id": str(self.id),
            "colour": self.colour,
            "logo": self.logo,
            "name": self.name,
            "text": self.text,
            "brand_type": self.brand_type,
        }

        return serialized


service_email_branding = db.Table(
    "service_email_branding",
    db.Model.metadata,
    # service_id is a primary key as you can only have one email branding per service
    db.Column(
        "service_id",
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        primary_key=True,
        nullable=False,
    ),
    db.Column(
        "email_branding_id",
        UUID(as_uuid=True),
        db.ForeignKey("email_branding.id"),
        nullable=False,
    ),
)


class Domain(db.Model):
    __tablename__ = "domain"
    domain = db.Column(db.String(255), primary_key=True)
    organization_id = db.Column(
        "organization_id",
        UUID(as_uuid=True),
        db.ForeignKey("organization.id"),
        nullable=False,
    )


class Organization(db.Model):
    __tablename__ = "organization"
    id = db.Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=False
    )
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )
    agreement_signed = db.Column(db.Boolean, nullable=True)
    agreement_signed_at = db.Column(db.DateTime, nullable=True)
    agreement_signed_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        nullable=True,
    )
    agreement_signed_by = db.relationship("User")
    agreement_signed_on_behalf_of_name = db.Column(db.String(255), nullable=True)
    agreement_signed_on_behalf_of_email_address = db.Column(
        db.String(255), nullable=True
    )
    agreement_signed_version = db.Column(db.Float, nullable=True)
    organization_type = enum_column(OrganizationType, unique=False, nullable=True)
    request_to_go_live_notes = db.Column(db.Text)

    domains = db.relationship("Domain")

    email_branding = db.relationship("EmailBranding")
    email_branding_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("email_branding.id"),
        nullable=True,
    )

    notes = db.Column(db.Text, nullable=True)
    purchase_order_number = db.Column(db.String(255), nullable=True)
    billing_contact_names = db.Column(db.Text, nullable=True)
    billing_contact_email_addresses = db.Column(db.Text, nullable=True)
    billing_reference = db.Column(db.String(255), nullable=True)

    @property
    def live_services(self):
        return [
            service
            for service in self.services
            if service.active and not service.restricted
        ]

    @property
    def domain_list(self):
        return [domain.domain for domain in self.domains]

    @property
    def agreement(self):
        try:
            active_agreements = [
                agreement
                for agreement in self.agreements
                if agreement.status == AgreementStatus.ACTIVE
            ]
            return active_agreements[0]
        except IndexError:
            return None

    @property
    def agreement_active(self):
        try:
            return self.agreement.status == AgreementStatus.ACTIVE
        except AttributeError:
            return False

    @property
    def has_mou(self):
        try:
            return self.agreement.type == AgreementType.MOU
        except AttributeError:
            return False

    def serialize(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "active": self.active,
            "organization_type": self.organization_type,
            "email_branding_id": self.email_branding_id,
            "agreement_signed": self.agreement_signed,
            "agreement_signed_at": self.agreement_signed_at,
            "agreement_signed_by_id": self.agreement_signed_by_id,
            "agreement_signed_on_behalf_of_name": self.agreement_signed_on_behalf_of_name,
            "agreement_signed_on_behalf_of_email_address": self.agreement_signed_on_behalf_of_email_address,
            "agreement_signed_version": self.agreement_signed_version,
            "domains": self.domain_list,
            "request_to_go_live_notes": self.request_to_go_live_notes,
            "count_of_live_services": len(self.live_services),
            "notes": self.notes,
            "purchase_order_number": self.purchase_order_number,
            "billing_contact_names": self.billing_contact_names,
            "billing_contact_email_addresses": self.billing_contact_email_addresses,
            "billing_reference": self.billing_reference,
        }

    def serialize_for_list(self):
        return {
            "name": self.name,
            "id": str(self.id),
            "active": self.active,
            "count_of_live_services": len(self.live_services),
            "domains": self.domain_list,
            "organization_type": self.organization_type,
        }


class Service(db.Model, Versioned):
    __tablename__ = "services"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False, unique=True)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=utc_now,
    )
    active = db.Column(
        db.Boolean,
        index=False,
        unique=False,
        nullable=False,
        default=True,
    )
    message_limit = db.Column(db.BigInteger, index=False, unique=False, nullable=False)
    total_message_limit = db.Column(
        db.BigInteger,
        index=False,
        unique=False,
        nullable=False,
    )
    restricted = db.Column(db.Boolean, index=False, unique=False, nullable=False)
    email_from = db.Column(db.Text, index=False, unique=True, nullable=False)
    created_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    prefix_sms = db.Column(db.Boolean, nullable=False, default=True)
    organization_type = enum_column(OrganizationType, unique=False, nullable=True)
    rate_limit = db.Column(db.Integer, index=False, nullable=False, default=3000)
    contact_link = db.Column(db.String(255), nullable=True, unique=False)
    volume_sms = db.Column(db.Integer(), nullable=True, unique=False)
    volume_email = db.Column(db.Integer(), nullable=True, unique=False)
    consent_to_research = db.Column(db.Boolean, nullable=True)
    count_as_live = db.Column(db.Boolean, nullable=False, default=True)
    go_live_user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        nullable=True,
    )
    go_live_user = db.relationship("User", foreign_keys=[go_live_user_id])
    go_live_at = db.Column(db.DateTime, nullable=True)

    organization_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("organization.id"),
        index=True,
        nullable=True,
    )
    organization = db.relationship("Organization", backref="services")

    notes = db.Column(db.Text, nullable=True)
    purchase_order_number = db.Column(db.String(255), nullable=True)
    billing_contact_names = db.Column(db.Text, nullable=True)
    billing_contact_email_addresses = db.Column(db.Text, nullable=True)
    billing_reference = db.Column(db.String(255), nullable=True)

    email_branding = db.relationship(
        "EmailBranding",
        secondary=service_email_branding,
        uselist=False,
        backref=db.backref("services", lazy="dynamic"),
    )

    @classmethod
    def from_json(cls, data):
        """
        Assumption: data has been validated appropriately.

        Returns a Service object based on the provided data. Deserialises created_by to created_by_id as marshmallow
        would.
        """
        # validate json with marshmallow
        fields = data.copy()

        fields["created_by_id"] = fields.pop("created_by")

        return cls(**fields)

    def get_inbound_number(self):
        if self.inbound_number and self.inbound_number.active:
            return self.inbound_number.number

    def get_default_sms_sender(self):
        # notify-api-1513 let's try a minimalistic fix
        # to see if we can get the right numbers back
        default_sms_sender = [
            x
            for x in self.service_sms_senders
            if x.is_default and x.service_id == self.id
        ]
        current_app.logger.info(
            f"#notify-api-1513 senders for service {self.name} are {self.service_sms_senders}"
        )
        return default_sms_sender[0].sms_sender

    def get_default_reply_to_email_address(self):
        default_reply_to = [x for x in self.reply_to_email_addresses if x.is_default]
        return default_reply_to[0].email_address if default_reply_to else None

    def has_permission(self, permission):
        return permission in [p.permission for p in self.permissions]

    def serialize_for_org_dashboard(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "active": self.active,
            "restricted": self.restricted,
        }


class AnnualBilling(db.Model):
    __tablename__ = "annual_billing"
    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=False,
    )
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        unique=False,
        index=True,
        nullable=False,
    )
    financial_year_start = db.Column(
        db.Integer,
        nullable=False,
        default=True,
        unique=False,
    )
    free_sms_fragment_limit = db.Column(
        db.Integer,
        nullable=False,
        index=False,
        unique=False,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    UniqueConstraint(
        "financial_year_start",
        "service_id",
        name="ix_annual_billing_service_id",
    )
    service = db.relationship(
        Service,
        backref=db.backref("annual_billing", uselist=True),
    )

    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "financial_year_start",
            name="uix_service_id_financial_year_start",
        ),
    )

    def serialize_free_sms_items(self):
        return {
            "free_sms_fragment_limit": self.free_sms_fragment_limit,
            "financial_year_start": self.financial_year_start,
        }

    def serialize(self):
        def serialize_service():
            return {"id": str(self.service_id), "name": self.service.name}

        return {
            "id": str(self.id),
            "free_sms_fragment_limit": self.free_sms_fragment_limit,
            "service_id": self.service_id,
            "financial_year_start": self.financial_year_start,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
            "service": serialize_service() if self.service else None,
        }


class InboundNumber(db.Model):
    __tablename__ = "inbound_numbers"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number = db.Column(db.String(255), unique=True, nullable=False)
    provider = db.Column(db.String(), nullable=False)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        unique=True,
        index=True,
        nullable=True,
    )
    service = db.relationship(
        Service,
        backref=db.backref("inbound_number", uselist=False),
    )
    active = db.Column(
        db.Boolean,
        index=False,
        unique=False,
        nullable=False,
        default=True,
    )
    created_at = db.Column(
        db.DateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )

    def serialize(self):
        def serialize_service():
            return {"id": str(self.service_id), "name": self.service.name}

        return {
            "id": str(self.id),
            "number": self.number,
            "provider": self.provider,
            "service": serialize_service() if self.service else None,
            "active": self.active,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class ServiceSmsSender(db.Model):
    __tablename__ = "service_sms_senders"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sms_sender = db.Column(db.String(11), nullable=False)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        nullable=False,
        unique=False,
    )
    service = db.relationship(
        Service,
        backref=db.backref("service_sms_senders", uselist=True),
    )
    is_default = db.Column(db.Boolean, nullable=False, default=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    inbound_number_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("inbound_numbers.id"),
        unique=True,
        index=True,
        nullable=True,
    )
    inbound_number = db.relationship(
        InboundNumber,
        backref=db.backref("inbound_number", uselist=False),
    )
    created_at = db.Column(
        db.DateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )

    def get_reply_to_text(self):
        return try_validate_and_format_phone_number(self.sms_sender)

    def serialize(self):
        return {
            "id": str(self.id),
            "sms_sender": self.sms_sender,
            "service_id": str(self.service_id),
            "is_default": self.is_default,
            "archived": self.archived,
            "inbound_number_id": (
                str(self.inbound_number_id) if self.inbound_number_id else None
            ),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class ServicePermission(db.Model):
    __tablename__ = "service_permissions"

    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        primary_key=True,
        index=True,
        nullable=False,
    )
    permission = enum_column(
        ServicePermissionType,
        index=True,
        primary_key=True,
        nullable=False,
    )
    created_at = db.Column(
        db.DateTime,
        default=utc_now,
        nullable=False,
    )

    service_permission_types = db.relationship(
        Service,
        backref=db.backref("permissions", cascade="all, delete-orphan"),
    )

    def __repr__(self):
        return "<{} has service permission: {}>".format(
            self.service_id, self.permission
        )


class ServiceGuestList(db.Model):
    __tablename__ = "service_whitelist"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        nullable=False,
    )
    service = db.relationship("Service", backref="guest_list")
    recipient_type = enum_column(RecipientType, nullable=False)
    recipient = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    @classmethod
    def from_string(cls, service_id, recipient_type, recipient):
        instance = cls(service_id=service_id, recipient_type=recipient_type)

        try:
            if recipient_type == RecipientType.MOBILE:
                instance.recipient = validate_phone_number(
                    recipient, international=True
                )
            elif recipient_type == RecipientType.EMAIL:
                instance.recipient = validate_email_address(recipient)
            else:
                raise ValueError("Invalid recipient type")
        except InvalidPhoneError:
            raise ValueError('Invalid guest list: "{}"'.format(recipient))
        except InvalidEmailError:
            raise ValueError('Invalid guest list: "{}"'.format(recipient))
        else:
            return instance

    def __repr__(self):
        return "Recipient {} of type: {}".format(self.recipient, self.recipient_type)


class ServiceInboundApi(db.Model, Versioned):
    __tablename__ = "service_inbound_api"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        nullable=False,
        unique=True,
    )
    service = db.relationship("Service", backref="inbound_api")
    url = db.Column(db.String(), nullable=False)
    _bearer_token = db.Column("bearer_token", db.String(), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.relationship("User")
    updated_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    @property
    def bearer_token(self):
        return encryption.decrypt(self._bearer_token)

    @bearer_token.setter
    def bearer_token(self, bearer_token):
        if bearer_token:
            self._bearer_token = encryption.encrypt(str(bearer_token))

    def serialize(self):
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "url": self.url,
            "updated_by_id": str(self.updated_by_id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class ServiceCallbackApi(db.Model, Versioned):
    __tablename__ = "service_callback_api"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        nullable=False,
    )
    service = db.relationship("Service", backref="service_callback_api")
    url = db.Column(db.String(), nullable=False)
    callback_type = enum_column(CallbackType, nullable=True)
    _bearer_token = db.Column("bearer_token", db.String(), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=utc_now,
        nullable=False,
    )
    updated_at = db.Column(db.DateTime, nullable=True)
    updated_by = db.relationship("User")
    updated_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "callback_type",
            name="uix_service_callback_type",
        ),
    )

    @property
    def bearer_token(self):
        return encryption.decrypt(self._bearer_token)

    @bearer_token.setter
    def bearer_token(self, bearer_token):
        if bearer_token:
            self._bearer_token = encryption.encrypt(str(bearer_token))

    def serialize(self):
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "url": self.url,
            "updated_by_id": str(self.updated_by_id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class ApiKey(db.Model, Versioned):
    __tablename__ = "api_keys"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    _secret = db.Column("secret", db.String(255), unique=True, nullable=False)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        nullable=False,
    )
    service = db.relationship("Service", backref="api_keys")
    key_type = enum_column(KeyType, index=True, nullable=False)
    expiry_date = db.Column(db.DateTime)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=utc_now,
    )
    created_by = db.relationship("User")
    created_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        index=True,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uix_service_to_key_name",
            "service_id",
            "name",
            unique=True,
            postgresql_where=expiry_date.is_(None),
        ),
    )

    @property
    def secret(self):
        return encryption.decrypt(self._secret)

    @secret.setter
    def secret(self, secret):
        if secret:
            self._secret = encryption.encrypt(str(secret))


class TemplateFolder(db.Model):
    __tablename__ = "template_folder"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        nullable=False,
    )
    name = db.Column(db.String, nullable=False)
    parent_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("template_folder.id"),
        nullable=True,
    )

    service = db.relationship("Service", backref="all_template_folders")
    parent = db.relationship("TemplateFolder", remote_side=[id], backref="subfolders")
    users = db.relationship(
        "ServiceUser",
        uselist=True,
        backref=db.backref(
            "folders", foreign_keys="user_folder_permissions.c.template_folder_id"
        ),
        secondary="user_folder_permissions",
        primaryjoin="TemplateFolder.id == user_folder_permissions.c.template_folder_id",
    )

    __table_args__ = (UniqueConstraint("id", "service_id", name="ix_id_service_id"), {})

    def serialize(self):
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "service_id": self.service_id,
            "users_with_permission": self.get_users_with_permission(),
        }

    def is_parent_of(self, other):
        while other.parent is not None:
            if other.parent == self:
                return True
            other = other.parent
        return False

    def get_users_with_permission(self):
        service_users = self.users
        users_with_permission = [
            str(service_user.user_id) for service_user in service_users
        ]

        return users_with_permission


template_folder_map = db.Table(
    "template_folder_map",
    db.Model.metadata,
    # template_id is a primary key as a template can only belong in one folder
    db.Column(
        "template_id",
        UUID(as_uuid=True),
        db.ForeignKey("templates.id"),
        primary_key=True,
        nullable=False,
    ),
    db.Column(
        "template_folder_id",
        UUID(as_uuid=True),
        db.ForeignKey("template_folder.id"),
        nullable=False,
    ),
)


class TemplateBase(db.Model):
    __abstract__ = True

    def __init__(self, **kwargs):
        if "template_type" in kwargs:
            self.template_type = kwargs.pop("template_type")

        super().__init__(**kwargs)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = db.Column(db.String(255), nullable=False)
    template_type = enum_column(TemplateType, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(db.DateTime, onupdate=utc_now)
    content = db.Column(db.Text, nullable=False)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    hidden = db.Column(db.Boolean, nullable=False, default=False)
    subject = db.Column(db.Text)

    @declared_attr
    def service_id(cls):
        return db.Column(
            UUID(as_uuid=True), db.ForeignKey("services.id"), index=True, nullable=False
        )

    @declared_attr
    def created_by_id(cls):
        return db.Column(
            UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False
        )

    @declared_attr
    def created_by(cls):
        return db.relationship("User")

    @declared_attr
    def process_type(cls):
        return enum_column(
            TemplateProcessType,
            index=True,
            nullable=False,
            default=TemplateProcessType.NORMAL,
        )

    redact_personalisation = association_proxy(
        "template_redacted", "redact_personalisation"
    )

    # TODO: possibly unnecessary after removing letters
    @property
    def reply_to(self):
        return None

    @reply_to.setter
    def reply_to(self, value):
        if value is None:
            pass
        else:
            raise ValueError(
                "Unable to set sender for {} template".format(self.template_type)
            )

    def get_reply_to_text(self):
        if self.template_type == TemplateType.EMAIL:
            return self.service.get_default_reply_to_email_address()
        elif self.template_type == TemplateType.SMS:
            return try_validate_and_format_phone_number(
                self.service.get_default_sms_sender()
            )
        else:
            return None

    def _as_utils_template(self):
        if self.template_type == TemplateType.EMAIL:
            return PlainTextEmailTemplate(self.__dict__)
        elif self.template_type == TemplateType.SMS:
            return SMSMessageTemplate(self.__dict__)
        else:
            raise ValueError(f"{self.template_type} is an invalid template type.")

    def _as_utils_template_with_personalisation(self, values):
        template = self._as_utils_template()
        template.values = values
        return template

    def serialize_for_v2(self):
        serialized = {
            "id": str(self.id),
            "type": self.template_type,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
            "created_by": self.created_by.email_address,
            "version": self.version,
            "body": self.content,
            "subject": (
                self.subject if self.template_type == TemplateType.EMAIL else None
            ),
            "name": self.name,
            "personalisation": {
                key: {
                    "required": True,
                }
                for key in self._as_utils_template().placeholders
            },
        }

        return serialized


class Template(TemplateBase):
    __tablename__ = "templates"

    service = db.relationship("Service", backref="templates")
    version = db.Column(db.Integer, default=0, nullable=False)

    folder = db.relationship(
        "TemplateFolder",
        secondary=template_folder_map,
        uselist=False,
        # eagerly load the folder whenever the template object is fetched
        lazy="joined",
        backref=db.backref("templates"),
    )

    def get_link(self):
        return url_for(
            "template.get_template_by_id_and_service_id",
            service_id=self.service_id,
            template_id=self.id,
            _external=True,
        )

    @classmethod
    def from_json(cls, data, folder):
        """
        Assumption: data has been validated appropriately.
        Returns a Template object based on the provided data.
        """
        fields = data.copy()

        fields["created_by_id"] = fields.pop("created_by")
        fields["service_id"] = fields.pop("service")
        fields["folder"] = folder
        return cls(**fields)


class TemplateRedacted(db.Model):
    __tablename__ = "template_redacted"

    template_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("templates.id"),
        primary_key=True,
        nullable=False,
    )
    redact_personalisation = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    updated_by = db.relationship("User")

    # uselist=False as this is a one-to-one relationship
    template = db.relationship(
        "Template",
        uselist=False,
        backref=db.backref("template_redacted", uselist=False),
    )


class TemplateHistory(TemplateBase):
    __tablename__ = "templates_history"

    service = db.relationship("Service")
    version = db.Column(db.Integer, primary_key=True, nullable=False)

    @declared_attr
    def template_redacted(cls):
        return db.relationship(
            "TemplateRedacted",
            foreign_keys=[cls.id],
            primaryjoin="TemplateRedacted.template_id == TemplateHistory.id",
        )

    def get_link(self):
        return url_for(
            "template.get_template_by_id_and_service_id",
            template_id=self.id,
            service_id=self.service.id,
            version=self.version,
            _external=True,
        )


class ProviderDetails(db.Model):
    __tablename__ = "provider_details"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, nullable=False)
    notification_type = enum_column(NotificationType, nullable=False)
    active = db.Column(db.Boolean, default=False, nullable=False)
    version = db.Column(db.Integer, default=1, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )
    created_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        index=True,
        nullable=True,
    )
    created_by = db.relationship("User")
    supports_international = db.Column(db.Boolean, nullable=False, default=False)


class ProviderDetailsHistory(db.Model, HistoryModel):
    __tablename__ = "provider_details_history"

    id = db.Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    display_name = db.Column(db.String, nullable=False)
    identifier = db.Column(db.String, nullable=False)
    notification_type = enum_column(NotificationType, nullable=False)
    active = db.Column(db.Boolean, nullable=False)
    version = db.Column(db.Integer, primary_key=True, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=utc_now)
    created_by_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=True
    )
    created_by = db.relationship("User")
    supports_international = db.Column(db.Boolean, nullable=False, default=False)


class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    original_file_name = db.Column(db.String, nullable=False)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        unique=False,
        nullable=False,
    )
    service = db.relationship("Service", backref=db.backref("jobs", lazy="dynamic"))
    template_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("templates.id"), index=True, unique=False
    )
    template = db.relationship("Template", backref=db.backref("jobs", lazy="dynamic"))
    template_version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=utc_now,
    )
    notification_count = db.Column(db.Integer, nullable=False)
    notifications_sent = db.Column(db.Integer, nullable=False, default=0)
    notifications_delivered = db.Column(db.Integer, nullable=False, default=0)
    notifications_failed = db.Column(db.Integer, nullable=False, default=0)

    processing_started = db.Column(
        db.DateTime, index=False, unique=False, nullable=True
    )
    processing_finished = db.Column(
        db.DateTime, index=False, unique=False, nullable=True
    )
    created_by = db.relationship("User")
    created_by_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=True
    )
    scheduled_for = db.Column(db.DateTime, index=True, unique=False, nullable=True)
    job_status = enum_column(
        JobStatus,
        index=True,
        nullable=False,
        default=JobStatus.PENDING,
    )
    archived = db.Column(db.Boolean, nullable=False, default=False)


class VerifyCode(db.Model):
    __tablename__ = "verify_codes"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id"), index=True, nullable=False
    )
    user = db.relationship("User", backref=db.backref("verify_codes", lazy="dynamic"))
    _code = db.Column(db.String, nullable=False)
    code_type = enum_column(CodeType, index=False, unique=False, nullable=False)
    expiry_datetime = db.Column(db.DateTime, nullable=False)
    code_used = db.Column(db.Boolean, default=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )

    @property
    def code(self):
        raise AttributeError("Code not readable")

    @code.setter
    def code(self, cde):
        self._code = hashpw(cde)

    def check_code(self, cde):
        return check_hash(cde, self._code)


class NotificationAllTimeView(db.Model):
    """
    WARNING: this view is a union of rows in "notifications" and
    "notification_history". Any query on this view will query both
    tables and therefore rely on *both* sets of indices.
    """

    __tablename__ = "notifications_all_time_view"

    # Tell alembic not to create this as a table. We have a migration where we manually set this up as a view.
    # This is custom logic we apply - not built-in logic. See `migrations/env.py`
    __table_args__ = {"info": {"managed_by_alembic": False}}

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    job_id = db.Column(UUID(as_uuid=True))
    job_row_number = db.Column(db.Integer)
    service_id = db.Column(UUID(as_uuid=True))
    template_id = db.Column(UUID(as_uuid=True))
    template_version = db.Column(db.Integer)
    api_key_id = db.Column(UUID(as_uuid=True))
    key_type = db.Column(db.String)
    billable_units = db.Column(db.Integer)
    notification_type = enum_column(NotificationType)
    created_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    sent_by = db.Column(db.String)
    updated_at = db.Column(db.DateTime)
    status = enum_column(
        NotificationStatus,
        name="notification_status",
        nullable=True,
        default=NotificationStatus.CREATED,
        key="status",
    )
    reference = db.Column(db.String)
    client_reference = db.Column(db.String)
    international = db.Column(db.Boolean)
    phone_prefix = db.Column(db.String)
    rate_multiplier = db.Column(db.Numeric(asdecimal=False))
    created_by_id = db.Column(UUID(as_uuid=True))
    document_download_count = db.Column(db.Integer)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    to = db.Column(db.String, nullable=False)
    normalised_to = db.Column(db.String, nullable=True)
    job_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("jobs.id"),
        index=True,
        unique=False,
    )
    job = db.relationship("Job", backref=db.backref("notifications", lazy="dynamic"))
    job_row_number = db.Column(db.Integer, nullable=True)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        unique=False,
    )
    service = db.relationship("Service")
    template_id = db.Column(UUID(as_uuid=True), index=True, unique=False)
    template_version = db.Column(db.Integer, nullable=False)
    template = db.relationship("TemplateHistory")
    api_key_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("api_keys.id"),
        unique=False,
    )
    api_key = db.relationship("ApiKey")
    key_type = enum_column(KeyType, unique=False, nullable=False)
    billable_units = db.Column(db.Integer, nullable=False, default=0)
    notification_type = enum_column(NotificationType, nullable=False)
    created_at = db.Column(db.DateTime, index=True, unique=False, nullable=False)
    sent_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    sent_by = db.Column(db.String, nullable=True)
    message_cost = db.Column(db.Float, nullable=True, default=0.0)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=utc_now,
    )
    status = enum_column(
        NotificationStatus,
        name="notification_status",
        nullable=True,
        default=NotificationStatus.CREATED,
        key="status",
    )
    reference = db.Column(db.String, nullable=True, index=True)
    client_reference = db.Column(db.String, index=True, nullable=True)
    _personalisation = db.Column(db.String, nullable=True)

    international = db.Column(db.Boolean, nullable=False, default=False)
    phone_prefix = db.Column(db.String, nullable=True)
    rate_multiplier = db.Column(db.Numeric(asdecimal=False), nullable=True)

    created_by = db.relationship("User")
    created_by_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True
    )

    reply_to_text = db.Column(db.String, nullable=True)

    document_download_count = db.Column(db.Integer, nullable=True)

    provider_response = db.Column(db.Text, nullable=True)
    carrier = db.Column(db.Text, nullable=True)
    message_id = db.Column(db.Text, nullable=True)

    # queue_name = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["templates_history.id", "templates_history.version"],
        ),
        UniqueConstraint(
            "job_id", "job_row_number", name="uq_notifications_job_row_number"
        ),
        Index(
            "ix_notifications_notification_type_composite",
            "notification_type",
            "status",
            "created_at",
        ),
        Index("ix_notifications_service_created_at", "service_id", "created_at"),
        Index(
            "ix_notifications_service_id_composite",
            "service_id",
            "notification_type",
            "status",
            "created_at",
        ),
    )

    @property
    def personalisation(self):
        if self._personalisation:
            try:
                return encryption.decrypt(self._personalisation)
            except EncryptionError:
                current_app.logger.exception(
                    "Error decrypting notification.personalisation, returning empty dict",
                )
        return {}

    @personalisation.setter
    def personalisation(self, personalisation):
        self._personalisation = encryption.encrypt(personalisation or {})

    def completed_at(self):
        if self.status in NotificationStatus.completed_types():
            return self.updated_at.strftime(DATETIME_FORMAT)

        return None

    @staticmethod
    def substitute_status(status_or_statuses):
        """
        static function that takes a status or list of statuses and substitutes our new failure types if it finds
        the deprecated one

        > IN
        'failed'

        < OUT
        ['technical-failure', 'temporary-failure', 'permanent-failure']

        -

        > IN
        ['failed', 'created', 'accepted']

        < OUT
        ['technical-failure', 'temporary-failure', 'permanent-failure', 'created', 'sending']


        -

        > IN
        'delivered'

        < OUT
        ['received']

        :param status_or_statuses: a single status or list of statuses
        :return: a single status or list with the current failure statuses substituted for 'failure'
        """

        def _substitute_status_str(_status):
            return (
                NotificationStatus.failed_types()
                if _status == NotificationStatus.FAILED
                else [_status]
            )

        def _substitute_status_seq(_statuses):
            return list(
                set(
                    itertools.chain.from_iterable(
                        _substitute_status_str(status) for status in _statuses
                    )
                )
            )

        if isinstance(status_or_statuses, str):
            return _substitute_status_str(status_or_statuses)
        return _substitute_status_seq(status_or_statuses)

    @property
    def content(self):
        return self.template._as_utils_template_with_personalisation(
            self.personalisation
        ).content_with_placeholders_filled_in

    @property
    def subject(self):
        template_object = self.template._as_utils_template_with_personalisation(
            self.personalisation
        )
        return getattr(template_object, "subject", None)

    @property
    def formatted_status(self):
        return {
            NotificationType.EMAIL: {
                NotificationStatus.FAILED: "Failed",
                NotificationStatus.TECHNICAL_FAILURE: "Technical failure",
                NotificationStatus.TEMPORARY_FAILURE: "Inbox not accepting messages right now",
                NotificationStatus.PERMANENT_FAILURE: "Email address doesn’t exist",
                NotificationStatus.DELIVERED: "Delivered",
                NotificationStatus.SENDING: "Sending",
                NotificationStatus.CREATED: "Sending",
                NotificationStatus.SENT: "Delivered",
            },
            NotificationType.SMS: {
                NotificationStatus.FAILED: "Failed",
                NotificationStatus.TECHNICAL_FAILURE: "Technical failure",
                NotificationStatus.TEMPORARY_FAILURE: "Unable to find carrier response -- still looking",
                NotificationStatus.PERMANENT_FAILURE: "Unable to find carrier response.",
                NotificationStatus.DELIVERED: "Delivered",
                NotificationStatus.PENDING: "Pending",
                NotificationStatus.SENDING: "Sending",
                NotificationStatus.CREATED: "Sending",
                NotificationStatus.SENT: "Sent internationally",
            },
        }[self.template.template_type].get(self.status, self.status)

    def get_created_by_name(self):
        if self.created_by:
            return self.created_by.name
        else:
            return None

    def get_created_by_email_address(self):
        if self.created_by:
            return self.created_by.email_address
        else:
            return None

    def serialize_for_redis(self, obj):
        if isinstance(obj.__class__, DeclarativeMeta):
            fields = {}
            for column in obj.__table__.columns:
                if column.name == "notification_status":
                    new_name = "status"
                    value = getattr(obj, new_name)
                elif column.name == "created_at":
                    if isinstance(obj.created_at, str):
                        value = obj.created_at
                    else:
                        value = (obj.created_at.strftime("%Y-%m-%d %H:%M:%S"),)
                elif column.name in ["sent_at", "completed_at"]:
                    value = None
                elif column.name.endswith("_id") or column.name == "id":
                    value = getattr(obj, column.name)
                    value = str(value)
                else:
                    value = getattr(obj, column.name)
                if column.name in ["message_id", "api_key_id"]:
                    pass  # do nothing because we don't have the message id yet
                else:
                    fields[column.name] = value

            return fields
        raise ValueError("Provided object is not a SQLAlchemy instance")

    def serialize_for_csv(self):
        serialized = {
            "row_number": (
                "" if self.job_row_number is None else self.job_row_number + 1
            ),
            "recipient": self.to,
            "client_reference": self.client_reference or "",
            "template_name": self.template.name,
            "template_type": self.template.template_type,
            "job_name": self.job.original_file_name if self.job else "",
            "carrier": self.carrier,
            "provider_response": self.provider_response,
            "status": self.formatted_status,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "created_by_name": self.get_created_by_name(),
            "created_by_email_address": self.get_created_by_email_address(),
        }

        return serialized

    def serialize(self):
        template_dict = {
            "version": self.template.version,
            "id": self.template.id,
            "uri": self.template.get_link(),
        }

        serialized = {
            "id": self.id,
            "reference": self.client_reference,
            "email_address": (
                self.to if self.notification_type == NotificationType.EMAIL else None
            ),
            "phone_number": (
                self.to if self.notification_type == NotificationType.SMS else None
            ),
            "line_1": None,
            "line_2": None,
            "line_3": None,
            "line_4": None,
            "line_5": None,
            "line_6": None,
            "postcode": None,
            "type": self.notification_type,
            "status": self.status,
            "provider_response": self.provider_response,
            "carrier": self.carrier,
            "template": template_dict,
            "body": self.content,
            "subject": self.subject,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "created_by_name": self.get_created_by_name(),
            "sent_at": get_dt_string_or_none(self.sent_at),
            "completed_at": self.completed_at(),
            "scheduled_for": None,
        }

        return serialized


class NotificationHistory(db.Model, HistoryModel):
    __tablename__ = "notification_history"

    id = db.Column(UUID(as_uuid=True), primary_key=True)
    job_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("jobs.id"),
        index=True,
        unique=False,
    )
    job = db.relationship("Job")
    job_row_number = db.Column(db.Integer, nullable=True)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        unique=False,
    )
    service = db.relationship("Service")
    template_id = db.Column(UUID(as_uuid=True), unique=False)
    template_version = db.Column(db.Integer, nullable=False)
    api_key_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("api_keys.id"),
        unique=False,
    )
    api_key = db.relationship("ApiKey")
    key_type = enum_column(KeyType, unique=False, nullable=False)
    billable_units = db.Column(db.Integer, nullable=False, default=0)
    notification_type = enum_column(NotificationType, nullable=False)
    created_at = db.Column(db.DateTime, unique=False, nullable=False)
    sent_at = db.Column(db.DateTime, index=False, unique=False, nullable=True)
    sent_by = db.Column(db.String, nullable=True)
    message_cost = db.Column(db.Float, nullable=True, default=0.0)
    updated_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=True,
        onupdate=utc_now,
    )
    status = enum_column(
        NotificationStatus,
        name="notification_status",
        nullable=True,
        default=NotificationStatus.CREATED,
        key="status",
    )
    reference = db.Column(db.String, nullable=True, index=True)
    client_reference = db.Column(db.String, nullable=True)

    international = db.Column(db.Boolean, nullable=True, default=False)
    phone_prefix = db.Column(db.String, nullable=True)
    rate_multiplier = db.Column(db.Numeric(asdecimal=False), nullable=True)

    created_by_id = db.Column(UUID(as_uuid=True), nullable=True)

    document_download_count = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.ForeignKeyConstraint(
            ["template_id", "template_version"],
            ["templates_history.id", "templates_history.version"],
        ),
        Index(
            "ix_notification_history_service_id_composite",
            "service_id",
            "key_type",
            "notification_type",
            "created_at",
        ),
    )

    @classmethod
    def from_original(cls, notification):
        history = super().from_original(notification)
        history.status = notification.status
        return history

    def update_from_original(self, original):
        super().update_from_original(original)
        self.status = original.status


class InvitedUser(db.Model):
    __tablename__ = "invited_users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address = db.Column(db.String(255), nullable=False)
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    from_user = db.relationship("User")
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        unique=False,
    )
    service = db.relationship("Service")
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    status = enum_column(
        InvitedUserStatus,
        nullable=False,
        default=InvitedUserStatus.PENDING,
    )
    permissions = db.Column(db.String, nullable=False)
    auth_type = enum_column(AuthType, index=True, nullable=False, default=AuthType.SMS)
    folder_permissions = db.Column(
        JSONB(none_as_null=True), nullable=False, default=list
    )

    # would like to have used properties for this but haven't found a way to make them
    # play nice with marshmallow yet
    def get_permissions(self):
        return self.permissions.split(",")


class InvitedOrganizationUser(db.Model):
    __tablename__ = "invited_organization_users"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_address = db.Column(db.String(255), nullable=False)
    invited_by_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        nullable=False,
    )
    invited_by = db.relationship("User")
    organization_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("organization.id"),
        nullable=False,
    )
    organization = db.relationship("Organization")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )

    status = enum_column(
        InvitedUserStatus,
        nullable=False,
        default=InvitedUserStatus.PENDING,
    )

    def serialize(self):
        return {
            "id": str(self.id),
            "email_address": self.email_address,
            "invited_by": str(self.invited_by_id),
            "organization": str(self.organization_id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "status": self.status,
        }


class Permission(db.Model):
    __tablename__ = "permissions"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Service id is optional, if the service is omitted we will assume the permission is not service specific.
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        unique=False,
        nullable=True,
    )
    service = db.relationship("Service")
    user_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    user = db.relationship("User")
    permission = enum_column(PermissionType, index=False, unique=False, nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "service_id",
            "user_id",
            "permission",
            name="uix_service_user_permission",
        ),
    )


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime,
        index=False,
        unique=False,
        nullable=False,
        default=utc_now,
    )
    data = db.Column(JSON, nullable=False)


class Rate(db.Model):
    __tablename__ = "rates"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    valid_from = db.Column(db.DateTime, nullable=False)
    rate = db.Column(db.Float(asdecimal=False), nullable=False)
    notification_type = enum_column(NotificationType, index=True, nullable=False)

    def __str__(self):
        return f"{self.rate} {self.notification_type} {self.valid_from}"


class InboundSms(db.Model):
    __tablename__ = "inbound_sms"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        nullable=False,
    )
    service = db.relationship("Service", backref="inbound_sms")

    notify_number = db.Column(
        db.String,
        nullable=False,
    )  # the service's number, that the msg was sent to
    user_number = db.Column(
        db.String,
        nullable=False,
        index=True,
    )  # the end user's number, that the msg was sent from
    provider_date = db.Column(db.DateTime)
    provider_reference = db.Column(db.String)
    provider = db.Column(db.String, nullable=False)
    _content = db.Column("content", db.String, nullable=False)

    @property
    def content(self):
        return encryption.decrypt(self._content)

    @content.setter
    def content(self, content):
        self._content = encryption.encrypt(content)

    def serialize(self):
        return {
            "id": str(self.id),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "service_id": str(self.service_id),
            "notify_number": self.notify_number,
            "user_number": self.user_number,
            "content": self.content,
        }


class InboundSmsHistory(db.Model, HistoryModel):
    __tablename__ = "inbound_sms_history"
    id = db.Column(UUID(as_uuid=True), primary_key=True)
    created_at = db.Column(db.DateTime, index=True, unique=False, nullable=False)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        index=True,
        unique=False,
    )
    service = db.relationship("Service")
    notify_number = db.Column(db.String, nullable=False)
    provider_date = db.Column(db.DateTime)
    provider_reference = db.Column(db.String)
    provider = db.Column(db.String, nullable=False)


class ServiceEmailReplyTo(db.Model):
    __tablename__ = "service_email_reply_to"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        unique=False,
        index=True,
        nullable=False,
    )
    service = db.relationship(Service, backref=db.backref("reply_to_email_addresses"))

    email_address = db.Column(db.Text, nullable=False, index=False, unique=False)
    is_default = db.Column(db.Boolean, nullable=False, default=True)
    archived = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )

    def serialize(self):
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "email_address": self.email_address,
            "is_default": self.is_default,
            "archived": self.archived,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class FactBilling(db.Model):
    __tablename__ = "ft_billing"

    local_date = db.Column(db.Date, nullable=False, primary_key=True, index=True)
    template_id = db.Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        index=True,
    )
    service_id = db.Column(
        UUID(as_uuid=True),
        nullable=False,
        primary_key=True,
        index=True,
    )
    notification_type = db.Column(db.Text, nullable=False, primary_key=True)
    provider = db.Column(db.Text, nullable=False, primary_key=True)
    rate_multiplier = db.Column(db.Integer(), nullable=False, primary_key=True)
    international = db.Column(db.Boolean, nullable=False, primary_key=True)
    rate = db.Column(db.Numeric(), nullable=False, primary_key=True)
    billable_units = db.Column(db.Integer(), nullable=True)
    notifications_sent = db.Column(db.Integer(), nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )


class FactNotificationStatus(db.Model):
    __tablename__ = "ft_notification_status"

    local_date = db.Column(db.Date, index=True, primary_key=True, nullable=False)
    template_id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        index=True,
        nullable=False,
    )
    service_id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        index=True,
        nullable=False,
    )
    job_id = db.Column(UUID(as_uuid=True), primary_key=True, index=True, nullable=False)
    notification_type = enum_column(NotificationType, primary_key=True, nullable=False)
    key_type = enum_column(KeyType, primary_key=True, nullable=False)
    notification_status = enum_column(
        NotificationStatus,
        primary_key=True,
        nullable=False,
    )
    notification_count = db.Column(db.Integer(), nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )


class FactProcessingTime(db.Model):
    __tablename__ = "ft_processing_time"

    local_date = db.Column(db.Date, index=True, primary_key=True, nullable=False)
    messages_total = db.Column(db.Integer(), nullable=False)
    messages_within_10_secs = db.Column(db.Integer(), nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )


class Complaint(db.Model):
    __tablename__ = "complaints"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notification_id = db.Column(UUID(as_uuid=True), index=True, nullable=False)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        unique=False,
        index=True,
        nullable=False,
    )
    service = db.relationship(Service, backref=db.backref("complaints"))
    ses_feedback_id = db.Column(db.Text, nullable=True)
    complaint_type = db.Column(db.Text, nullable=True)
    complaint_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )

    def serialize(self):
        return {
            "id": str(self.id),
            "notification_id": str(self.notification_id),
            "service_id": str(self.service_id),
            "service_name": self.service.name,
            "ses_feedback_id": str(self.ses_feedback_id),
            "complaint_type": self.complaint_type,
            "complaint_date": get_dt_string_or_none(self.complaint_date),
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
        }


class ServiceDataRetention(db.Model):
    __tablename__ = "service_data_retention"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("services.id"),
        unique=False,
        index=True,
        nullable=False,
    )
    service = db.relationship(
        Service,
        backref=db.backref(
            "data_retention",
            collection_class=attribute_mapped_collection("notification_type"),
        ),
    )
    notification_type = enum_column(NotificationType, nullable=False)
    days_of_retention = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "service_id", "notification_type", name="uix_service_data_retention"
        ),
    )

    def serialize(self):
        return {
            "id": str(self.id),
            "service_id": str(self.service_id),
            "service_name": self.service.name,
            "notification_type": self.notification_type,
            "days_of_retention": self.days_of_retention,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class WebauthnCredential(db.Model):
    """
    A table that stores data for registered webauthn credentials.
    """

    __tablename__ = "webauthn_credential"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid.uuid4,
    )

    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    user = db.relationship(User, backref=db.backref("webauthn_credentials"))

    name = db.Column(db.String, nullable=False)

    # base64 encoded CBOR. used for logging in. https://w3c.github.io/webauthn/#sctn-attested-credential-data
    credential_data = db.Column(db.String, nullable=False)

    # base64 encoded CBOR. used for auditing. https://www.w3.org/TR/webauthn-2/#authenticatorattestationresponse
    registration_response = db.Column(db.String, nullable=False)

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=True,
        onupdate=utc_now,
    )

    def serialize(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "credential_data": self.credential_data,
            "created_at": self.created_at.strftime(DATETIME_FORMAT),
            "updated_at": get_dt_string_or_none(self.updated_at),
        }


class Agreement(db.Model):
    __tablename__ = "agreements"
    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=False,
    )
    type = enum_column(AgreementType, index=False, unique=False, nullable=False)
    partner_name = db.Column(db.String(255), nullable=False, unique=True, index=True)
    status = enum_column(AgreementStatus, index=False, unique=False, nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    url = db.Column(db.String(255), nullable=False, unique=True, index=True)
    budget_amount = db.Column(db.Float, nullable=True)
    organization_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("organization.id"),
        nullable=True,
    )
    organization = db.relationship("Organization", backref="agreements")

    def serialize(self):
        return {
            "id": str(self.id),
            "type": self.type,
            "partner_name": self.partner_name,
            "status": self.status,
            "start_time": self.start_time.strftime(DATETIME_FORMAT),
            "end_time": self.end_time.strftime(DATETIME_FORMAT),
            "budget_amount": self.budget_amount,
            "organization_id": self.organization_id,
        }
