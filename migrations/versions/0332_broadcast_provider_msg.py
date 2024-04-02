"""

Revision ID: 0332_broadcast_provider_msg
Revises: 0331_add_broadcast_org
Create Date: 2020-10-26 16:28:11.917468

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0332_broadcast_provider_msg"
down_revision = "0331_add_broadcast_org"

STATUSES = [
    "technical-failure",
    "sending",
    "returned-ack",
    "returned-error",
]


def upgrade():
    broadcast_provider_message_status_type = op.create_table(
        "broadcast_provider_message_status_type",
        sa.Column("name", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )
    op.bulk_insert(
        broadcast_provider_message_status_type,
        [{"name": status} for status in STATUSES],
    )

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "broadcast_provider_message",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broadcast_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["broadcast_event_id"],
            ["broadcast_event.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("broadcast_event_id", "provider"),
    )


def downgrade():
    op.drop_table("broadcast_provider_message")
    op.drop_table("broadcast_provider_message_status_type")
