"""

Revision ID: 0212_remove_caseworking
Revises: 0211_email_branding_update
Create Date: 2018-07-31 18:00:20.457755

"""
from alembic import op

revision = "0212_remove_caseworking"
down_revision = "0211_email_branding_update"


def upgrade():
    op.execute("delete from service_permissions where permission = 'caseworking'")
    op.execute("delete from service_permission_types where name = 'caseworking'")


def downgrade():
    op.execute("insert into service_permission_types values('caseworking')")
