"""
 Revision ID: 0219_default_email_branding
Revises: 0217_default_email_branding
Create Date: 2018-08-24 13:36:49.346156
 """
from alembic import op
from sqlalchemy import text

from app.models import BRANDING_ORG

revision = '0219_default_email_branding'
down_revision = '0217_default_email_branding'


def upgrade():
    conn = op.get_bind()
    input_params = {
        "branding_org": BRANDING_ORG
    }
    conn.execute(text("""
        update
            email_branding
        set
            brand_type = :branding_org
        where
            brand_type is null
    """), input_params)


def downgrade():
    pass
