"""

Revision ID: 0321_notification_history_pivot
Revises: 0320_optimise_notifications
Create Date: 2020-03-26 11:16:12.389524

"""
import os

from alembic import op

revision = '0321_notification_history_pivot'
down_revision = '0320_optimise_notifications'
environment = os.environ['NOTIFY_ENVIRONMENT']


def upgrade():
    op.execute('CREATE TABLE notification_history_pivot AS SELECT * FROM notification_history WHERE 1=2')
    op.execute('ALTER TABLE notification_history_pivot ADD PRIMARY KEY (id)')


def downgrade():
    op.execute('DROP TABLE notifications_history_pivot')
