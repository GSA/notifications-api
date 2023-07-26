"""
 Revision ID: 0217_default_email_branding
Revises: 0216_remove_colours
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op

revision = '0217_default_email_branding'
down_revision = '0216_remove_colours'


def upgrade():
    op.execute("""
        update
            email_branding
        set
            brand_type = 'org'
        where
            brand_type = null
    """)


def downgrade():
    pass
