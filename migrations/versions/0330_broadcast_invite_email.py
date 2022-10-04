"""

Revision ID: 0330_broadcast_invite_email
Revises: 0329_purge_broadcast_data
Create Date: 2020-09-15 14:17:01.963181

"""

# revision identifiers, used by Alembic.
from datetime import datetime

from alembic import op

revision = '0330_broadcast_invite_email'
down_revision = '0329_purge_broadcast_data'

user_id = '6af522d0-2915-4e52-83a3-3690455a5fe6'
service_id = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
template_id = '46152f7c-6901-41d5-8590-a5624d0d4359'

def upgrade():
    pass


def downgrade():
    pass
