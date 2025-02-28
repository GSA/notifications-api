"""

Revision ID: 0415_add_message_cost
Revises: 0414_change_total_message_limit
Create Date: 2025-02-28 11:35:22.873930

"""

import sqlalchemy as sa
from alembic import op

down_revision = "0414_change_total_message_limit"
revision = "0415_add_message_cost"


def upgrade():
    op.add_column("notifications", sa.Column("message_cost", sa.Float))
    op.add_column("notification_history", sa.Column("message_cost", sa.Float))


def downgrade():
    op.drop_column("notifications", "message_cost")
    op.add_column("notification_history", sa.Column("message_cost", sa.Float))
