"""

Revision ID: 0392_drop_letter_permissions
Revises: 0391_update_sms_numbers
Create Date: 2023-03-06 08:55:24.153687

"""
from alembic import op

revision = "0392_drop_letter_permissions"
down_revision = "0391_update_sms_numbers"


def upgrade():
    op.execute("DELETE FROM permissions WHERE permission = 'send_letters'")


def downgrade():
    # not able to put the permissions back, but we can just pretend it worked fine.
    pass
