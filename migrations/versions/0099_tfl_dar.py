"""empty message

Revision ID: 0099_tfl_dar
Revises: 0098_service_inbound_api
Create Date: 2017-06-05 16:15:17.744908

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = "0099_tfl_dar"
down_revision = "0098_service_inbound_api"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

TFL_DAR_ID = "1d70f564-919b-4c68-8bdf-b8520d92516e"


def upgrade():
    conn = op.get_bind()
    input_params = {"tfl_dar_id": TFL_DAR_ID}
    conn.execute(
        text("""INSERT INTO organisation VALUES (
        :tfl_dar_id,
        '',
        'tfl_dar_x2.png',
        'tfl'
    )"""),
        input_params,
    )


def downgrade():
    conn = op.get_bind()
    input_params = {"tfl_dar_id": TFL_DAR_ID}
    conn.execute(
        text("""
        DELETE FROM organisation WHERE "id" = :tfl_dar_id
    """),
        input_params,
    )
