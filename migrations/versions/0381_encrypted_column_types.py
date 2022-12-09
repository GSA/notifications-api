"""

Revision ID: 0381_encrypted_column_types
Revises: 0380_bst_to_local
Create Date: 2022-12-09 10:17:03.358405

"""
from alembic import op
import sqlalchemy as sa


revision = '0381_encrypted_column_types'
down_revision = '0380_bst_to_local'


def upgrade():
    op.alter_column("api_keys", "secret", type_=sa.types.String())


def downgrade():
    op.alter_column("api_keys", "secret", type_=sa.types.String(length=255))
