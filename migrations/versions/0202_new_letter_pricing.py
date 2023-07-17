"""empty message

Revision ID: 0202_new_letter_pricing
Revises: 0198_add_caseworking_permission
Create Date: 2017-07-09 12:44:16.815039

"""
from sqlalchemy import text

revision = '0202_new_letter_pricing'
down_revision = '0198_add_caseworking_permission'

import uuid
from datetime import datetime
from alembic import op


start = datetime(2018, 6, 30, 23, 0)

NEW_RATES = [
    (uuid.uuid4(), start, 4, 0.39, True, 'second'),
    (uuid.uuid4(), start, 4, 0.51, False, 'second'),
    (uuid.uuid4(), start, 5, 0.42, True, 'second'),
    (uuid.uuid4(), start, 5, 0.57, False, 'second'),
]


def upgrade():
    conn = op.get_bind()
    for id, start_date, sheet_count, rate, crown, post_class in NEW_RATES:
        input_params = {
            "id": id,
            "start_date": start_date,
            "sheet_count": sheet_count,
            "rate": rate,
            "crown": crown,
            "post_class": post_class
        }
        conn.execute(text("""
            INSERT INTO letter_rates (id, start_date, sheet_count, rate, crown, post_class)
                VALUES (:id, :start_date, :sheet_count, :rate, :crown, :post_class)
        """), input_params)


def downgrade():
    pass
