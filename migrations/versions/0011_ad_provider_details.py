"""empty message

Revision ID: 0011_ad_provider_details
Revises: 0010_events_table
Create Date: 2016-05-05 09:14:29.328841

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = "0011_ad_provider_details"
down_revision = "0010_events_table"

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade():
    op.create_table(
        "provider_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("identifier", sa.String(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column(
            "notification_type",
            sa.Enum("email", "sms", "letter", name="notification_type"),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "provider_statistics",
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        op.f("ix_provider_statistics_provider_id"),
        "provider_statistics",
        ["provider_id"],
        unique=False,
    )
    op.create_foreign_key(
        "provider_stats_to_provider_fk",
        "provider_statistics",
        "provider_details",
        ["provider_id"],
        ["id"],
    )

    conn = op.get_bind()

    input_params = {"id": uuid.uuid4()}
    conn.execute(
        text(
            "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active) values (:id, 'AWS SES', 'ses', 10, 'email', true)"
        ),
        input_params,
    )
    input_params = {"id": uuid.uuid4()}
    conn.execute(
        text(
            "INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active) values (:id, 'AWS SNS', 'sns', 10, 'sms', true)"
        ),
        input_params,
    )
    op.execute(
        "UPDATE provider_statistics set provider_id = (select id from provider_details where identifier = 'ses') where provider = 'ses'"
    )
    op.execute(
        "UPDATE provider_statistics set provider_id = (select id from provider_details where identifier = 'sns') where provider = 'sns'"
    )


def downgrade():
    op.drop_index(
        op.f("ix_provider_statistics_provider_id"), table_name="provider_statistics"
    )
    op.drop_column("provider_statistics", "provider_id")
    op.drop_table("provider_details")
    op.execute("drop type notification_type")
