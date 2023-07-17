"""empty message

Revision ID: 0160_another_letter_org
Revises: 0159_add_historical_redact
Create Date: 2017-06-29 12:44:16.815039

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = '0160_another_letter_org'
down_revision = '0159_add_historical_redact'

from alembic import op


NEW_ORGANISATIONS = [
    ('501', 'Environment Agency (PDF letters ONLY)'),
]


def upgrade():
    conn = op.get_bind()

    for numeric_id, name in NEW_ORGANISATIONS:
        input_params = {
            "numeric_id": numeric_id,
            "name": name
        }
        conn.execute(text("INSERT INTO dvla_organisation VALUES (:numeric_id, :name)"), input_params)


def downgrade():
    conn = op.get_bind()
    for numeric_id, _ in NEW_ORGANISATIONS:
        input_params = {
            "numeric_id": numeric_id
        }
        conn.execute(text("DELETE FROM dvla_organisation WHERE id = :numeric_id"), input_params)
