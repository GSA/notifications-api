"""
 Revision ID: 0219_default_email_branding
Revises: 0216_remove_colours
Create Date: 2018-08-24 13:36:49.346156
"""

from alembic import op
from sqlalchemy import text

from app.enums import BrandType

revision = "0219_default_email_branding"
down_revision = "0216_remove_colours"


def upgrade():
    conn = op.get_bind()
    input_params = {"branding_org": BrandType.ORG.value}
    conn.execute(
        text(
            """
        update
            email_branding
        set
            brand_type = :branding_org
        where
            brand_type is null
    """
        ),
        input_params,
    )


def downgrade():
    pass
