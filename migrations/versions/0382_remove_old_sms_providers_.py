"""

Revision ID: 0382_remove_old_sms_providers
Revises: 0381_encrypted_column_types
Create Date: 2022-12-16 12:52:14.182717

"""
from alembic import op
import sqlalchemy as sa


revision = '0382_remove_old_providers'
down_revision = '0381_encrypted_column_types'


def upgrade():
    pass
    # op.execute("DELETE FROM provider_details WHERE identifier IN ('mmg', 'firetext')")
    # op.execute("DELETE FROM provider_details_history WHERE identifier IN ('mmg', 'firetext')")


def downgrade():
    raise Exception("Irreversible migration")
