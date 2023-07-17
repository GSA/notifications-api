"""empty message

Revision ID: 0091_letter_billing
Revises: 0090_inbound_sms
Create Date: 2017-05-31 11:43:55.744631

"""
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = '0091_letter_billing'
down_revision = '0090_inbound_sms'


def upgrade():
    op.create_table('letter_rates',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('valid_from', sa.DateTime(), nullable=False),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_table('letter_rate_details',
                    sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('letter_rate_id', postgresql.UUID(as_uuid=True), nullable=False),
                    sa.Column('page_total', sa.Integer(), nullable=False),
                    sa.Column('rate', sa.Numeric(), nullable=False),
                    sa.ForeignKeyConstraint(['letter_rate_id'], ['letter_rates.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_letter_rate_details_letter_rate_id'), 'letter_rate_details', ['letter_rate_id'],
                    unique=False)

    conn = op.get_bind()
    letter_id = uuid.uuid4()
    input_params = {
        "letter_id": letter_id
    }
    conn.execute(text("insert into letter_rates(id, valid_from) values(:letter_id, '2017-03-31 23:00:00')"), input_params)
    insert_details = "insert into letter_rate_details(id, letter_rate_id, page_total, rate) values(:id, :letter_id, :page_total, :rate)"
    input_params = {
        "id": uuid.uuid4(),
        "letter_id": letter_id,
        "page_total": 1,
        "rate": 29.3
    }
    conn.execute(text(insert_details), input_params)
    input_params = {
        "id": uuid.uuid4(),
        "letter_id": letter_id,
        "page_total": 2,
        "rate": 32
    }
    conn.execute(text(insert_details), input_params)
    input_params = {
        "id": uuid.uuid4(),
        "letter_id": letter_id,
        "page_total": 3,
        "rate": 35
    }
    conn.execute(text(insert_details), input_params)


def downgrade():
    op.get_bind()
    op.drop_index('ix_letter_rate_details_letter_rate_id')
    op.drop_table('letter_rate_details')
    op.drop_table('letter_rates')
