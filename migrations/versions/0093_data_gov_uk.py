"""empty message

Revision ID: 0093_data_gov_uk
Revises: 0092_add_inbound_provider
Create Date: 2017-06-05 16:15:17.744908

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = '0093_data_gov_uk'
down_revision = '0092_add_inbound_provider'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

DATA_GOV_UK_ID = '123496d4-44cb-4324-8e0a-4187101f4bdc'

input_params = {
    "data_gov_uk_id": DATA_GOV_UK_ID
}


def upgrade():
    conn = op.get_bind()
    conn.execute(text("INSERT INTO organisation VALUES (:data_gov_uk_id,'', 'data_gov_uk_x2.png', 'data gov.uk')"),
                 input_params)


def downgrade():
    conn = op.get_bind()
    conn.execute(text("DELETE FROM organisation WHERE id = :data_gov_uk_id"), input_params)
