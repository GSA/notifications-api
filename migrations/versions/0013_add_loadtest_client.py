"""empty message

Revision ID: 0013_add_loadtest_client
Revises: 0012_complete_provider_details
Create Date: 2016-05-05 09:14:29.328841

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = '0013_add_loadtest_client'
down_revision = '0012_complete_provider_details'

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    conn = op.get_bind()
    input_params = {
        "id": uuid.uuid4()
    }
    conn.execute(
        text("INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active) values (:id, 'Loadtesting', 'loadtesting', 30, 'sms', true)"), input_params
    )


def downgrade():
    op.drop_table('provider_details')
