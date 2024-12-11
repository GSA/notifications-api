"""

Revision ID: 0413_add_message_id
Revises: 412_remove_priority
Create Date: 2023-12-11 11:35:22.873930

"""

import sqlalchemy as sa
from alembic import op

revision = "0413_add_message_id"
down_revision = "0412_remove_priority"


def upgrade():
    op.add_column("notifications", sa.Column("message_id", sa.Text))


def downgrade():
    op.drop_column("notifications", "message_id")
