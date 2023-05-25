"""

Revision ID: 0395_remove_international_letters_permission
Revises: 0394_remove_contact_list
Create Date: 2023-05-23 10:03:10.485368

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0395_remove_intl_letters_perm'
down_revision = '0394_remove_contact_list'


def upgrade():
    sql = """
        DELETE
        FROM service_permissions
        WHERE permission = 'international_letters'
    """

    conn = op.get_bind()
    conn.execute(sql)


def downgrade():
    pass
