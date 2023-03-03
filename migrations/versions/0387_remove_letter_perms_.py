"""

Revision ID: 0387_remove_letter_perms_.py
Revises: 0386_remove_letter_rates_.py
Create Date: 2023-02-17 11:56:00.993409

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0387_remove_letter_perms_.py'
down_revision = '0386_remove_letter_rates_.py'


def upgrade():
    # this is the inverse of migration 0317
    op.execute("DELETE from service_permissions where permission = 'upload_letters'")
    # ### end Alembic commands ###


def downgrade():
    # this is the inverse of migration 0317
     op.execute("""
        INSERT INTO
            service_permissions (service_id, permission, created_at)
        SELECT
            id, 'upload_letters', now()
        FROM
            services
        WHERE
            NOT EXISTS (
                SELECT
                FROM
                    service_permissions
                WHERE
                    service_id = services.id and
                    permission = 'upload_letters'
           )
    """)
    # ### end Alembic commands ###
