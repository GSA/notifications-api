"""

Revision ID: 0262_remove_edit_folders
Revises: 0261_service_volumes
Create Date: 2019-02-15 11:20:25.812823

"""

from alembic import op
from sqlalchemy import text

revision = "0262_remove_edit_folders"
down_revision = "0261_service_volumes"


def upgrade():
    op.execute("DELETE from service_permissions where permission = 'edit_folders'")


def downgrade():
    conn = op.get_bind()
    input_params = {"permission": "edit_folders"}
    conn.execute(
        text("""
           INSERT INTO
               service_permissions (service_id, permission, created_at)
           SELECT
               id, :permission, now()
           FROM
               services
           WHERE
               NOT EXISTS (
                   SELECT
                   FROM
                       service_permissions
                   WHERE
                       service_id = services.id and
                       permission = :permission
               )
       """),
        input_params,
    )
