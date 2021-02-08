"""

Revision ID: 0343_org_billing_details
Revises: 0342_service_broadcast_settings
Create Date: 2021-02-01 14:40:14.809632

"""
from alembic import op
import sqlalchemy as sa


revision = '0343_org_billing_details'
down_revision = '0342_service_broadcast_settings'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('organisation', sa.Column('billing_contact_email_addresses', sa.Text(), nullable=True))
    op.add_column('organisation', sa.Column('billing_contact_names', sa.Text(), nullable=True))
    op.add_column('organisation', sa.Column('billing_reference', sa.String(length=255), nullable=True))
    op.add_column('organisation', sa.Column('notes', sa.Text(), nullable=True))
    op.add_column('organisation', sa.Column('purchase_order_number', sa.String(length=255), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('organisation', 'purchase_order_number')
    op.drop_column('organisation', 'notes')
    op.drop_column('organisation', 'billing_reference')
    op.drop_column('organisation', 'billing_contact_names')
    op.drop_column('organisation', 'billing_contact_email_addresses')
    # ### end Alembic commands ###
