"""empty message

Revision ID: 0214_another_letter_org
Revises: 0213_brand_colour_domain_

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = '0214_another_letter_org'
down_revision = '0213_brand_colour_domain'

from alembic import op


NEW_ORGANISATIONS = [
    ('510', 'Pension Wise'),
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
