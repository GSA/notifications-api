"""

Revision ID: 0411_add_login_uuid
Revises: 410_enums_for_everything
Create Date: 2023-04-24 11:35:22.873930

"""

import sqlalchemy as sa
from alembic import op

revision = "0411_add_login_uuid"
down_revision = "0410_enums_for_everything"


def upgrade():
    op.add_column("users", sa.Column("login_uuid", sa.Text))


def downgrade():
    op.drop_column("users", "login_uuid")
