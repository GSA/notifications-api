"""empty message

Revision ID: 0377_add_inbound_sms_number
Revises: 0376_add_provider_response
Create Date: 2022-09-30 11:04:15.888017

"""
import uuid

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = "0377_add_inbound_sms_number"
down_revision = "0376_add_provider_response"

INBOUND_NUMBER_ID = "9b5bc009-b847-4b1f-8a54-f3b5f95cff18"
INBOUND_NUMBER = current_app.config["NOTIFY_INTERNATIONAL_SMS_SENDER"].strip("+")
DEFAULT_SERVICE_ID = current_app.config["NOTIFY_SERVICE_ID"]


def upgrade():
    conn = op.get_bind()

    # delete the previous inbound_number with mmg as provider
    # table_name = 'inbound_numbers'
    # select_by_col = 'number'
    # select_by_val = INBOUND_NUMBER
    input_params = {"inbound_number": INBOUND_NUMBER}
    conn.execute(
        text("delete from inbound_numbers where number =:inbound_number"), input_params
    )

    input_params = {
        "inbound_number_id": INBOUND_NUMBER_ID,
        "inbound_number": INBOUND_NUMBER,
        "default_service_id": DEFAULT_SERVICE_ID,
    }
    # add the inbound number for the default service to inbound_numbers
    conn.execute(
        text(
            "insert into inbound_numbers "
            "(id, number, provider, service_id, active, created_at) "
            "VALUES (:inbound_number_id, :inbound_number, 'sns', :default_service_id, 'true', now())"
        ),
        input_params,
    )

    input_params = {"inbound_number": INBOUND_NUMBER}
    # add the inbound number for the default service to service_sms_senders
    conn.execute(
        text(
            "update service_sms_senders set sms_sender=:inbound_number "
            "where id = '286d6176-adbe-7ea7-ba26-b7606ee5e2a4'"
        ),
        input_params,
    )

    # add the inbound number for the default service to inbound_numbers
    input_params = {"default_service_id": DEFAULT_SERVICE_ID}
    conn.execute(
        text(
            "insert into service_permissions (service_id, permission, created_at) "
            "VALUES(:default_service_id, 'inbound_sms', now())"
        ),
        input_params,
    )
    # pass


def downgrade():
    conn = op.get_bind()
    input_params = {"inbound_number_id": INBOUND_NUMBER_ID}
    conn.execute(
        text(
            "delete from service_sms_senders where inbound_number_id = :inbound_number_id"
        ),
        input_params,
    )
    input_params = {"inbound_number": INBOUND_NUMBER}
    conn.execute(
        text("delete from inbound_numbers where number = :inbound_number"), input_params
    )
    input_params = {"default_service_id": DEFAULT_SERVICE_ID}
    conn.execute(
        text(
            "delete from service_permissions "
            "where service_id = :default_service_id and permission = 'inbound_sms'"
        ),
        input_params,
    )
    input_params = {"inbound_number": INBOUND_NUMBER}
    conn.execute(
        text(
            "insert into inbound_numbers (id, number, provider, service_id, active, created_at) "
            "VALUES('d7aea27f-340b-4428-9b20-4470dd978bda', :inbound_number, 'mmg', 'null', 'false', 'now()')"
        ),
        input_params,
    )
    # pass
