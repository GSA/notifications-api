"""empty message

Revision ID: 0066_add_dvla_provider
Revises: 0065_users_current_session_id
Create Date: 2017-03-02 10:32:28.984947

"""
import uuid
from datetime import datetime

from sqlalchemy import text

revision = '0066_add_dvla_provider'
down_revision = '0065_users_current_session_id'

from alembic import op


def upgrade():
    conn = op.get_bind()
    provider_id = str(uuid.uuid4())
    input_params = {
        "provider_id": provider_id
    }
    conn.execute(
        text("INSERT INTO provider_details (id, display_name, identifier, priority, notification_type, active, version) values (:provider_id, 'DVLA', 'dvla', 50, 'letter', true, 1)"), input_params
    )
    conn.execute(
        text("INSERT INTO provider_details_history (id, display_name, identifier, priority, notification_type, active, version) values (:provider_id, 'DVLA', 'dvla', 50, 'letter', true, 1)"), input_params
    )
    input_params = {
        "id": uuid.uuid4(),
        "time_now": datetime.utcnow(),
        "provider_id": provider_id
    }
    conn.execute(
        text("INSERT INTO provider_rates (id, valid_from, rate, provider_id) VALUES (:id, :time_now, 1.0, :provider_id)"),
        input_params
    )


def downgrade():
    op.execute("DELETE FROM provider_rates where provider_id = (SELECT id from provider_details where display_name='DVLA')")
    op.execute("DELETE FROM provider_details_history where display_name = 'DVLA'")
    op.execute("DELETE FROM provider_details where display_name = 'DVLA'")
