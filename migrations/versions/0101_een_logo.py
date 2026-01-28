"""empty message

Revision ID: 0101_een_logo
Revises: 0100_notification_created_by
Create Date: 2017-06-26 11:43:30.374723

"""

from alembic import op
from sqlalchemy import text

revision = "0101_een_logo"
down_revision = "0100_notification_created_by"


ENTERPRISE_EUROPE_NETWORK_ID = "89ce468b-fb29-4d5d-bd3f-d468fb6f7c36"


def upgrade():
    input_params = {"network_id": ENTERPRISE_EUROPE_NETWORK_ID}
    conn = op.get_bind()
    conn.execute(
        text("""INSERT INTO organisation VALUES (
        :network_id,
        '',
        'een_x2.png',
        'een'
    )"""),
        input_params,
    )


def downgrade():
    input_params = {"network_id": ENTERPRISE_EUROPE_NETWORK_ID}
    conn = op.get_bind()
    conn.execute(
        text("""
        DELETE FROM organisation WHERE "id" = :network_id
    """),
        input_params,
    )
