"""

Revision ID: 0414_change_total_message_limit
Revises: 413_add_message_id
Create Date: 2025-01-23 11:35:22.873930

"""

import sqlalchemy as sa
from alembic import op

down_revision = "0413_add_message_id"
revision = "0414_change_total_message_limit"


def upgrade():
    """
    This limit is only used
    """
    op.execute("UPDATE services set total_message_limit=100000")



def downgrade():
    op.execute("UPDATE services set total_message_limit=250000")
