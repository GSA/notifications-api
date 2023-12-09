"""

Revision ID: 0397_rename_organisation_2
Revises: 0396_rename_organisation
Create Date: 2023-07-13 09:33:52.455290

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0397_rename_organisation_2"
down_revision = "0396_rename_organisation"


def upgrade():
    op.execute("ALTER TABLE organisation_types RENAME to organization_types")


def downgrade():
    op.execute("ALTER TABLE organization_types RENAME to organisation_types")
