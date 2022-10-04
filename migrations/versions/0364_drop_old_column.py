"""

Revision ID: 0364_drop_old_column
Revises: 0363_cancelled_by_api_key
Create Date: 2022-01-25 18:05:27.750234

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0364_drop_old_column'
down_revision = '0363_cancelled_by_api_key'


def upgrade():
    pass


def downgrade():
    pass
