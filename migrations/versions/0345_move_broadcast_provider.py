"""

Revision ID: 0345_move_broadcast_provider
Revises: 0344_stubbed_not_nullable
Create Date: 2021-02-09 09:19:07.957980

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0345_move_broadcast_provider"
down_revision = "0344_stubbed_not_nullable"


def upgrade():
    op.add_column(
        "service_broadcast_settings", sa.Column("provider", sa.String(), nullable=True)
    )

    sql = """
        select service_id, provider
        from service_broadcast_provider_restriction
        where service_id NOT IN (select service_id from service_broadcast_settings)
        """
    insert_sql = """
        insert into service_broadcast_settings(service_id, channel, provider, created_at, updated_at)
        values(:service_id, 'test', :provider, now(), null)
    """
    conn = op.get_bind()
    results = conn.execute(sql)
    restrictions = results.fetchall()
    for x in restrictions:
        input_params = {"service_id": x.service_id, "provider": x.provider}
        conn.execute(text(insert_sql), input_params)


def downgrade():
    # Downgrade does not try and fully undo the upgrade, in particular it does not
    # delete the rows added to the service_broadcast_settings table
    op.drop_column("service_broadcast_settings", "provider")
