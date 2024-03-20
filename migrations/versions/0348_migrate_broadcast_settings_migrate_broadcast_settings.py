"""

Revision ID: 0348_migrate_broadcast_settings
Revises: 0347_add_dvla_volumes_template
Create Date: 2021-02-18 15:25:30.667098

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision = "0348_migrate_broadcast_settings"
down_revision = "0347_add_dvla_volumes_template"


def upgrade():
    # For every service that has the broadcast permission we want it to have
    # a row in the broadcast_service_settings table
    #
    # If it doesnt have a row already, then:
    # - if the service is in trial mode, add a row and set the channel as 'severe'
    # - if the service is in live mode, add a row and set the channel as 'test'
    #
    # If it does have a row already no action needed
    conn = op.get_bind()

    find_services_sql = """
    SELECT services.id, services.restricted
    FROM services
    LEFT JOIN service_permissions
    ON services.id = service_permissions.service_id
    WHERE service_permissions.permission = 'broadcast'
    """

    services = conn.execute(find_services_sql)
    for service in services:
        input_params = {"service_id": service.id}
        setting = conn.execute(
            text(
                "SELECT service_id, channel, provider FROM service_broadcast_settings WHERE service_id=:service_id;"
            ),
            input_params,
        ).first()
        if setting:
            print(
                f"Service {service.id} already has service_broadcast_settings. No action required"
            )
        else:
            channel = "severe" if service.restricted else "test"
            print(
                f"Service {service.id} does not have service_broadcast_settings. Will insert one with channel {channel}"
            )
            input_params = {"service_id": service.id, "channel": channel}
            conn.execute(
                text(
                    "INSERT INTO service_broadcast_settings (service_id, channel, created_at) "
                    "VALUES (:service_id, :channel, now());"
                ),
                input_params,
            )


def downgrade():
    # No downgrade as we do not know what the state of the table was before that it should return to
    pass
