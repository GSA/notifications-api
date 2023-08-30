"""empty message

Revision ID: 0198_add_caseworking_permission
Revises: 0197_service_contact_link
Create Date: 2018-02-21 12:05:00

"""

# revision identifiers, used by Alembic.
from sqlalchemy import text

revision = "0198_add_caseworking_permission"
down_revision = "0197_service_contact_link"

from alembic import op

PERMISSION_NAME = "caseworking"


def upgrade():
    conn = op.get_bind()
    input_params = {"permission_name": PERMISSION_NAME}
    conn.execute(
        text("insert into service_permission_types values(:permission_name)"),
        input_params,
    )


def downgrade():
    conn = op.get_bind()
    input_params = {"permission_name": PERMISSION_NAME}
    conn.execute(
        text("delete from service_permissions where permission = :permission_name"),
        input_params,
    )
    conn.execute(
        text("delete from service_permission_types where name = :permission_name"),
        input_params,
    )
