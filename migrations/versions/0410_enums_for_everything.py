"""

Revision ID: 0410_enums_for_everything
Revises: 0409_fix_service_name
Create Date: 2024-01-18 12:34:32.857422

"""
from enum import Enum
from typing import TypedDict

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.enums import (
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
    RecipientType,
    ServicePermissionType,
    TemplateProcessType,
    TemplateType,
)

revision = "0410_enums_for_everything"
down_revision = "0409_fix_service_name"


class EnumValues(TypedDict):
    values: list[str]
    name: str


_enum_params: dict[Enum, EnumValues] = {
    KeyType: {"values": ["normal", "team", "test"], "name": "key_types"},
    BrandType: {
        "values": ["govuk", "org", "both", "org_banner"],
        "name": "brand_types",
    },
    InvitedUserStatus: {
        "values": ["pending", "accepted", "cancelled", "expired"],
        "name": "invited_user_statuses",
    },
    AuthType: {
        "values": ["sms_auth", "email_auth", "webauthn_auth"],
        "name": "auth_types",
    },
    JobStatus: {
        "values": [
            "pending",
            "in progress",
            "finished",
            "sending limits exceeded",
            "scheduled",
            "cancelled",
            "ready to send",
            "sent to dvla",
            "error",
        ],
        "name": "job_statuses",
    },
    NotificationStatus: {
        "values": [
            "cancelled",
            "created",
            "sending",
            "sent",
            "delivered",
            "pending",
            "failed",
            "technical-failure",
            "temporary-failure",
            "permanent-failure",
            "pending-virus-check",
            "validation-failed",
            "virus-scan-failed",
        ],
        "name": "notify_statuses",
    },
    NotificationType: {
        "values": ["sms", "email", "letter"],
        "name": "notification_types",
    },
    OrganizationType: {
        "values": ["federal", "state", "other"],
        "name": "organization_types",
    },
    CallbackType: {
        "values": ["delivery_status", "complaint"],
        "name": "callback_types",
    },
    ServicePermissionType: {
        "values": [
            "email",
            "sms",
            "international_sms",
            "inbound_sms",
            "schedule_notifications",
            "email_auth",
            "upload_document",
            "edit_folder_permissions",
        ],
        "name": "service_permission_types",
    },
    RecipientType: {"values": ["mobile", "email"], "name": "recipient_types"},
    TemplateType: {"values": ["sms", "email", "letter"], "name": "template_types"},
    TemplateProcessType: {
        "values": ["normal", "priority"],
        "name": "template_process_types",
    },
    CodeType: {"values": ["email", "sms"], "name": "code_types"},
}


def enum_type(enum: Enum) -> sa.Enum:
    return sa.Enum(*_enum_params[enum]["values"], name=_enum_params[enum]["name"])


def upgrade():
    # Remove foreign key constraints for old "helper" tables.
    op.drop_constraint("api_keys_key_type_fkey", "api_keys", type_="foreignkey")
    op.drop_constraint(
        "email_branding_brand_type_fkey", "email_branding", type_="foreignkey"
    )
    op.drop_constraint(
        "invited_organisation_users_status_fkey",
        "invited_organization_users",
        type_="foreignkey",
    )
    op.drop_constraint(
        "invited_users_auth_type_fkey", "invited_users", type_="foreignkey"
    )
    op.drop_constraint("jobs_job_status_fkey", "jobs", type_="foreignkey")
    op.drop_constraint(
        "notification_history_key_type_fkey", "notification_history", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_notification_history_notification_status",
        "notification_history",
        type_="foreignkey",
    )
    op.drop_constraint(
        "notifications_key_type_fkey", "notifications", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_notifications_notification_status", "notifications", type_="foreignkey"
    )
    op.drop_constraint(
        "organisation_organisation_type_fkey", "organization", type_="foreignkey"
    )
    op.drop_constraint(
        "service_callback_api_type_fk", "service_callback_api", type_="foreignkey"
    )
    op.drop_constraint(
        "service_permissions_permission_fkey", "service_permissions", type_="foreignkey"
    )
    op.drop_constraint(
        "services_organisation_type_fkey", "services", type_="foreignkey"
    )
    op.drop_constraint("templates_process_type_fkey", "templates", type_="foreignkey")
    op.drop_constraint(
        "templates_history_process_type_fkey", "templates_history", type_="foreignkey"
    )
    op.drop_constraint("users_auth_type_fkey", "users", type_="foreignkey")

    # Drop composite indexes
    op.drop_index("ix_notifications_service_id_composite", table_name="notifications")
    op.drop_index(
        "ix_notifications_notification_type_composite", table_name="notifications"
    )

    # drop old "helper" tables
    op.drop_table("template_process_type")
    op.drop_table("key_types")
    op.drop_table("service_callback_type")
    op.drop_table("auth_type")
    op.drop_table("organization_types")
    op.drop_table("invite_status_type")
    op.drop_table("branding_type")
    op.drop_table("notification_status_types")
    op.drop_table("job_status")
    op.drop_table("service_permission_types")

    # alter existing columns to use new enums
    op.alter_column(
        "api_keys",
        "key_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(KeyType),
        existing_nullable=False,
    )
    op.alter_column(
        "api_keys_history",
        "key_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(KeyType),
        existing_nullable=False,
    )
    op.alter_column(
        "email_branding",
        "brand_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(BrandType),
        existing_nullable=False,
    )
    op.alter_column(
        "invited_organization_users",
        "status",
        existing_type=sa.VARCHAR(),
        type_=enum_type(InvitedUserStatus),
        existing_nullable=False,
    )
    op.alter_column(
        "invited_users",
        "status",
        existing_type=postgresql.ENUM(
            "pending",
            "accepted",
            "cancelled",
            "expired",
            name="invited_users_status_types",
        ),
        type_=enum_type(InvitedUserStatus),
        existing_nullable=False,
    )
    op.alter_column(
        "invited_users",
        "auth_type",
        existing_type=sa.VARCHAR(),
        type_=enum_type(AuthType),
        existing_nullable=False,
        existing_server_default=sa.text("'sms_auth'::character varying"),
    )
    op.alter_column(
        "jobs",
        "job_status",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(JobStatus),
        existing_nullable=False,
    )
    op.alter_column(
        "notification_history",
        "notification_status",
        existing_type=sa.TEXT(),
        type_=enum_type(NotificationStatus),
        existing_nullable=True,
    )
    op.alter_column(
        "notification_history",
        "key_type",
        existing_type=sa.VARCHAR(),
        type_=enum_type(KeyType),
        existing_nullable=False,
    )
    op.alter_column(
        "notification_history",
        "notification_type",
        existing_type=postgresql.ENUM(
            "email", "sms", "letter", name="notification_type"
        ),
        type_=enum_type(NotificationType),
        existing_nullable=False,
    )
    op.alter_column(
        "notifications",
        "notification_status",
        existing_type=sa.TEXT(),
        type_=enum_type(NotificationStatus),
        existing_nullable=True,
    )
    op.alter_column(
        "notifications",
        "key_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(KeyType),
        existing_nullable=False,
    )
    op.alter_column(
        "notifications",
        "notification_type",
        existing_type=postgresql.ENUM(
            "email", "sms", "letter", name="notification_type"
        ),
        type_=enum_type(NotificationType),
        existing_nullable=False,
    )
    op.alter_column(
        "notifications", "international", existing_type=sa.BOOLEAN(), nullable=False
    )
    op.alter_column(
        "organization",
        "organization_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(OrganizationType),
        existing_nullable=True,
    )
    op.alter_column(
        "provider_details",
        "notification_type",
        existing_type=postgresql.ENUM(
            "email", "sms", "letter", name="notification_type"
        ),
        type_=enum_type(NotificationType),
        existing_nullable=False,
    )
    op.alter_column(
        "provider_details_history",
        "notification_type",
        existing_type=postgresql.ENUM(
            "email", "sms", "letter", name="notification_type"
        ),
        type_=enum_type(NotificationType),
        existing_nullable=False,
    )
    op.alter_column(
        "rates",
        "notification_type",
        existing_type=postgresql.ENUM(
            "email", "sms", "letter", name="notification_type"
        ),
        type_=enum_type(NotificationType),
        existing_nullable=False,
    )
    op.alter_column(
        "service_callback_api",
        "callback_type",
        existing_type=sa.VARCHAR(),
        type_=enum_type(CallbackType),
        existing_nullable=True,
    )
    op.alter_column(
        "service_callback_api_history",
        "callback_type",
        existing_type=sa.VARCHAR(),
        type_=enum_type(CallbackType),
        existing_nullable=True,
    )
    op.alter_column(
        "service_data_retention",
        "notification_type",
        existing_type=postgresql.ENUM(
            "email", "sms", "letter", name="notification_type"
        ),
        type_=enum_type(NotificationType),
        existing_nullable=False,
    )
    op.alter_column(
        "service_permissions",
        "permission",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(ServicePermissionType),
        existing_nullable=False,
    )
    op.alter_column(
        "service_whitelist",
        "recipient_type",
        existing_type=postgresql.ENUM("mobile", "email", name="recipient_type"),
        type_=enum_type(RecipientType),
        existing_nullable=False,
    )
    op.alter_column(
        "services",
        "organization_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(OrganizationType),
        existing_nullable=True,
    )
    op.alter_column(
        "services_history",
        "organization_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(OrganizationType),
        existing_nullable=True,
    )
    op.alter_column(
        "templates",
        "template_type",
        existing_type=postgresql.ENUM(
            "sms", "email", "letter", "broadcast", name="template_type"
        ),
        type_=enum_type(TemplateType),
        existing_nullable=False,
    )
    op.alter_column(
        "templates",
        "process_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(TemplateProcessType),
        existing_nullable=False,
    )
    op.alter_column(
        "templates_history",
        "template_type",
        existing_type=postgresql.ENUM(
            "sms", "email", "letter", "broadcast", name="template_type"
        ),
        type_=enum_type(TemplateType),
        existing_nullable=False,
    )
    op.alter_column(
        "templates_history",
        "process_type",
        existing_type=sa.VARCHAR(length=255),
        type_=enum_type(TemplateProcessType),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "auth_type",
        existing_type=sa.VARCHAR(),
        type_=enum_type(AuthType),
        existing_nullable=False,
        existing_server_default=sa.text("'sms_auth'::character varying"),
    )
    op.alter_column(
        "verify_codes",
        "code_type",
        existing_type=postgresql.ENUM("email", "sms", name="verify_code_types"),
        type_=enum_type(CodeType),
        existing_nullable=False,
    )

    # Recreate composite indexes
    op.create_index(
        "ix_notifications_service_id_composite",
        "notifications",
        ["service_id", "notification_type", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_notification_type_composite",
        "notifications",
        ["notification_type", "status", "created_at"],
        unique=False,
    )

    # ### end Alembic commands ###


def downgrade():
    # Dropping composite indexes
    op.drop_index("ix_notifications_service_id_composite", table_name="notifications")
    op.drop_index(
        "ix_notifications_notification_type_composite", table_name="notifications"
    )

    # Alter columns back
    op.alter_column(
        "verify_codes",
        "code_type",
        existing_type=enum_type(CodeType),
        type_=postgresql.ENUM("email", "sms", name="verify_code_types"),
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "auth_type",
        existing_type=enum_type(AuthType),
        type_=sa.VARCHAR(),
        existing_nullable=False,
        existing_server_default=sa.text("'sms_auth'::character varying"),
    )
    op.alter_column(
        "templates_history",
        "process_type",
        existing_type=enum_type(TemplateProcessType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "templates_history",
        "template_type",
        existing_type=enum_type(TemplateType),
        type_=postgresql.ENUM(
            "sms", "email", "letter", "broadcast", name="template_type"
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "templates",
        "process_type",
        existing_type=enum_type(TemplateProcessType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "templates",
        "template_type",
        existing_type=enum_type(TemplateType),
        type_=postgresql.ENUM(
            "sms", "email", "letter", "broadcast", name="template_type"
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "services_history",
        "organization_type",
        existing_type=enum_type(OrganizationType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "services",
        "organization_type",
        existing_type=enum_type(OrganizationType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "service_whitelist",
        "recipient_type",
        existing_type=enum_type(RecipientType),
        type_=postgresql.ENUM("mobile", "email", name="recipient_type"),
        existing_nullable=False,
    )
    op.alter_column(
        "service_permissions",
        "permission",
        existing_type=enum_type(ServicePermissionType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "service_data_retention",
        "notification_type",
        existing_type=enum_type(NotificationType),
        type_=postgresql.ENUM("email", "sms", "letter", name="notification_type"),
        existing_nullable=False,
    )
    op.alter_column(
        "service_callback_api_history",
        "callback_type",
        existing_type=enum_type(CallbackType),
        type_=sa.VARCHAR(),
        existing_nullable=True,
    )
    op.alter_column(
        "service_callback_api",
        "callback_type",
        existing_type=enum_type(CallbackType),
        type_=sa.VARCHAR(),
        existing_nullable=True,
    )
    op.alter_column(
        "rates",
        "notification_type",
        existing_type=enum_type(NotificationType),
        type_=postgresql.ENUM("email", "sms", "letter", name="notification_type"),
        existing_nullable=False,
    )
    op.alter_column(
        "provider_details_history",
        "notification_type",
        existing_type=enum_type(NotificationType),
        type_=postgresql.ENUM("email", "sms", "letter", name="notification_type"),
        existing_nullable=False,
    )
    op.alter_column(
        "provider_details",
        "notification_type",
        existing_type=enum_type(NotificationType),
        type_=postgresql.ENUM("email", "sms", "letter", name="notification_type"),
        existing_nullable=False,
    )
    op.alter_column(
        "organization",
        "organization_type",
        existing_type=enum_type(OrganizationType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "notifications",
        "notification_status",
        existing_type=enum_type(NotificationStatus),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "notifications",
        "notification_type",
        existing_type=enum_type(NotificationType),
        type_=postgresql.ENUM("email", "sms", "letter", name="notification_type"),
        existing_nullable=False,
    )
    op.alter_column(
        "notifications",
        "key_type",
        existing_type=enum_type(KeyType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "notification_history",
        "notification_status",
        existing_type=enum_type(NotificationStatus),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "notification_history",
        "notification_type",
        existing_type=enum_type(NotificationType),
        type_=postgresql.ENUM("email", "sms", "letter", name="notification_type"),
        existing_nullable=False,
    )
    op.alter_column(
        "notification_history",
        "key_type",
        existing_type=enum_type(KeyType),
        type_=sa.VARCHAR(),
        existing_nullable=False,
    )
    op.alter_column(
        "jobs",
        "job_status",
        existing_type=enum_type(JobStatus),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "invited_users",
        "auth_type",
        existing_type=enum_type(AuthType),
        type_=sa.VARCHAR(),
        existing_nullable=False,
        existing_server_default=sa.text("'sms_auth'::character varying"),
    )
    op.alter_column(
        "invited_users",
        "status",
        existing_type=enum_type(InvitedUserStatus),
        type_=postgresql.ENUM(
            "pending",
            "accepted",
            "cancelled",
            "expired",
            name="invited_users_status_types",
        ),
        existing_nullable=False,
    )
    op.alter_column(
        "invited_organization_users",
        "status",
        existing_type=enum_type(InvitedUserStatus),
        type_=sa.VARCHAR(),
        existing_nullable=False,
    )
    op.alter_column(
        "email_branding",
        "brand_type",
        existing_type=enum_type(BrandType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "api_keys_history",
        "key_type",
        existing_type=enum_type(KeyType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        "api_keys",
        "key_type",
        existing_type=enum_type(KeyType),
        type_=sa.VARCHAR(length=255),
        existing_nullable=False,
    )

    # Recreate helper tables
    service_permission_types = op.create_table(
        "service_permission_types",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="service_permission_types_pkey"),
    )
    op.bulk_insert(
        service_permission_types,
        [
            {"name": "letter"},
            {"name": "international_sms"},
            {"name": "sms"},
            {"name": "email"},
            {"name": "inbound_sms"},
            {"name": "schedule_notifications"},
            {"name": "email_auth"},
            {"name": "letters_as_pdf"},
            {"name": "upload_document"},
            {"name": "edit_folder_permissions"},
            {"name": "upload_letters"},
            {"name": "international_letters"},
            {"name": "broadcast}"},
        ],
    )
    job_status = op.create_table(
        "job_status",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="job_status_pkey"),
    )
    op.bulk_insert(
        job_status,
        [
            {"name": "pending"},
            {"name": "in progress"},
            {"name": "finished"},
            {"name": "sending limits exceeded"},
            {"name": "scheduled"},
            {"name": "cancelled"},
            {"name": "ready to send"},
            {"name": "sent to dvla"},
            {"name": "error"},
        ],
    )
    notification_status_types = op.create_table(
        "notification_status_types",
        sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="notification_status_types_pkey"),
    )
    op.bulk_insert(
        notification_status_types,
        [
            {"name": "created"},
            {"name": "pending"},
            {"name": "temporary-failure"},
            {"name": "delivered"},
            {"name": "sent"},
            {"name": "sending"},
            {"name": "failed"},
            {"name": "permanent-failure"},
            {"name": "technical-failure"},
            {"name": "pending-virus-check"},
            {"name": "virus-scan-failed"},
            {"name": "cancelled"},
            {"name": "returned-letter"},
            {"name": "validation-failed"},
        ],
    )
    branding_type = op.create_table(
        "branding_type",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="branding_type_pkey"),
    )
    op.bulk_insert(
        branding_type,
        [
            {"name": "org"},
            {"name": "both"},
            {"name": "org_banner"},
        ],
    )
    invite_status_type = op.create_table(
        "invite_status_type",
        sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="invite_status_type_pkey"),
    )
    op.bulk_insert(
        invite_status_type,
        [
            {"name": "pending"},
            {"name": "accepted"},
            {"name": "cancelled"},
        ],
    )
    organization_types = op.create_table(
        "organization_types",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.Column(
            "annual_free_sms_fragment_limit",
            sa.BIGINT(),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("name", name="organisation_types_pkey"),
    )
    op.bulk_insert(
        organization_types,
        [
            {"name": "other", "annual_free_sms_fragment_limit": 25000},
            {"name": "state", "annual_free_sms_fragment_limit": 250000},
            {"name": "federal", "annual_free_sms_fragment_limit": 250000},
        ],
    )
    auth_type = op.create_table(
        "auth_type",
        sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="auth_type_pkey"),
    )
    op.bulk_insert(
        auth_type,
        [
            {"name": "email_auth"},
            {"name": "sms_auth"},
            {"name": "webauthn_auth"},
        ],
    )
    service_callback_type = op.create_table(
        "service_callback_type",
        sa.Column("name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="service_callback_type_pkey"),
    )
    op.bulk_insert(
        service_callback_type,
        [
            {"name": "delivery_status"},
            {"name": "complaint"},
        ],
    )
    key_types = op.create_table(
        "key_types",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="key_types_pkey"),
    )
    op.bulk_insert(
        key_types,
        [
            {"name": "normal"},
            {"name": "team"},
            {"name": "test"},
        ],
    )
    template_process_type = op.create_table(
        "template_process_type",
        sa.Column("name", sa.VARCHAR(length=255), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint("name", name="template_process_type_pkey"),
    )
    op.bulk_insert(
        template_process_type,
        [
            {"name": "normal"},
            {"name": "priority"},
        ],
    )

    # Creating composite indexes
    op.create_index(
        "ix_notifications_service_id_composite",
        "notifications",
        ["service_id", "notification_type", "notification_status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_notification_type_composite",
        "notifications",
        ["notification_type", "notification_status", "created_at"],
        unique=False,
    )

    # Recreate foreign keys
    op.create_foreign_key(
        "users_auth_type_fkey", "users", "auth_type", ["auth_type"], ["name"]
    )
    op.create_foreign_key(
        "templates_history_process_type_fkey",
        "templates_history",
        "template_process_type",
        ["process_type"],
        ["name"],
    )
    op.create_foreign_key(
        "templates_process_type_fkey",
        "templates",
        "template_process_type",
        ["process_type"],
        ["name"],
    )
    op.create_foreign_key(
        "services_organisation_type_fkey",
        "services",
        "organization_types",
        ["organization_type"],
        ["name"],
    )
    op.create_foreign_key(
        "service_permissions_permission_fkey",
        "service_permissions",
        "service_permission_types",
        ["permission"],
        ["name"],
    )
    op.create_foreign_key(
        "service_callback_api_type_fk",
        "service_callback_api",
        "service_callback_type",
        ["callback_type"],
        ["name"],
    )
    op.create_foreign_key(
        "organisation_organisation_type_fkey",
        "organization",
        "organization_types",
        ["organization_type"],
        ["name"],
    )
    op.create_foreign_key(
        "fk_notifications_notification_status",
        "notifications",
        "notification_status_types",
        ["notification_status"],
        ["name"],
    )
    op.create_foreign_key(
        "notifications_key_type_fkey",
        "notifications",
        "key_types",
        ["key_type"],
        ["name"],
    )
    op.create_foreign_key(
        "fk_notification_history_notification_status",
        "notification_history",
        "notification_status_types",
        ["notification_status"],
        ["name"],
    )
    op.create_foreign_key(
        "notification_history_key_type_fkey",
        "notification_history",
        "key_types",
        ["key_type"],
        ["name"],
    )
    op.create_foreign_key(
        "jobs_job_status_fkey", "jobs", "job_status", ["job_status"], ["name"]
    )
    op.create_foreign_key(
        "invited_users_auth_type_fkey",
        "invited_users",
        "auth_type",
        ["auth_type"],
        ["name"],
    )
    op.create_foreign_key(
        "invited_organisation_users_status_fkey",
        "invited_organization_users",
        "invite_status_type",
        ["status"],
        ["name"],
    )
    op.create_foreign_key(
        "email_branding_brand_type_fkey",
        "email_branding",
        "branding_type",
        ["brand_type"],
        ["name"],
    )
    op.create_foreign_key(
        "api_keys_key_type_fkey", "api_keys", "key_types", ["key_type"], ["name"]
    )
