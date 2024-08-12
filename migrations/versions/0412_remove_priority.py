"""

Revision ID: 0412_remove_priority
Revises: 411_add_login_uuid

"""

import sqlalchemy as sa
from alembic import op

revision = "0412_remove_priority"
down_revision = "0411_add_login_uuid"


def upgrade():
    op.drop_column("provider_details", sa.Column("priority"))
    op.drop_column("provider_details_history", sa.Column("priority"))


def downgrade():
    op.add_column("provider_details", sa.Column("priority", sa.Integer()))
    op.add_column("provider_details_history", sa.Column("priority", sa.Integer()))
