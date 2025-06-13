"""

Revision ID: 0417_change_total_message_limit
Revises: 0416_readd_e2e_test_user
Create Date: 2025-06-12 11:35:22.873930

"""

import sqlalchemy as sa
from alembic import op

down_revision = "0416_readd_e2e_test_user"
revision = "0417_change_total_message_limit"


def upgrade():
    op.execute(
        "UPDATE services set total_message_limit=5000000 where total_message_limit=100000"
    )


def downgrade():
    op.execute(
        "UPDATE services set total_message_limit=100000 where total_message_limit=5000000"
    )
