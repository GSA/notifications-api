"""

Revision ID: 5f05ff382f15
Revises: 0379_remove_broadcasts
Create Date: 2022-11-21 11:35:51.987539

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0380_bst_to_local'
down_revision = '0379_remove_broadcasts'


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('ft_billing', 'bst_date', new_column_name='local_date')
    op.drop_index('ix_ft_billing_bst_date', table_name='ft_billing')
    op.create_index(op.f('ix_ft_billing_local_date'), 'ft_billing', ['local_date'], unique=False)

    op.alter_column('ft_notification_status', 'bst_date', new_column_name='local_date')
    op.drop_index('ix_ft_notification_status_bst_date', table_name='ft_notification_status')
    op.create_index(op.f('ix_ft_notification_status_local_date'), 'ft_notification_status', ['local_date'], unique=False)
    
    op.alter_column('ft_processing_time', 'bst_date', new_column_name='local_date')
    op.drop_index('ix_ft_processing_time_bst_date', table_name='ft_processing_time')
    op.create_index(op.f('ix_ft_processing_time_local_date'), 'ft_processing_time', ['local_date'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('ft_processing_time', 'local_date', new_column_name='bst_date')
    op.drop_index(op.f('ix_ft_processing_time_local_date'), table_name='ft_processing_time')
    op.create_index('ix_ft_processing_time_bst_date', 'ft_processing_time', ['bst_date'], unique=False)
    
    op.alter_column('ft_notification_status', 'local_date', new_column_name='bst_date')
    op.drop_index(op.f('ix_ft_notification_status_local_date'), table_name='ft_notification_status')
    op.create_index('ix_ft_notification_status_bst_date', 'ft_notification_status', ['bst_date'], unique=False)
    
    op.alter_column('ft_billing', 'local_date', new_column_name='bst_date')
    op.drop_index(op.f('ix_ft_billing_local_date'), table_name='ft_billing')
    op.create_index('ix_ft_billing_bst_date', 'ft_billing', ['bst_date'], unique=False)
    # ### end Alembic commands ###
