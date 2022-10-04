"""

Revision ID: 0348_migrate_broadcast_settings
Revises: 0347_add_dvla_volumes_template
Create Date: 2021-02-18 15:25:30.667098

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0348_migrate_broadcast_settings'
down_revision = '0347_add_dvla_volumes_template'


def upgrade():
    pass

def downgrade():
    pass
