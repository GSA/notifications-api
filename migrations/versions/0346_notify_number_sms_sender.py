"""

Revision ID: 0346_notify_number_sms_sender
Revises: 0345_move_broadcast_provider
Create Date: 2021-02-17 10:40:10.181087

"""
import uuid

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = '0346_notify_number_sms_sender'
down_revision = '0345_move_broadcast_provider'

SMS_SENDER_ID = 'd24b830b-57b4-4f14-bd80-02f46f8d54de'
NOTIFY_SERVICE_ID = current_app.config['NOTIFY_SERVICE_ID']
INBOUND_NUMBER = current_app.config['NOTIFY_INTERNATIONAL_SMS_SENDER'].strip('+')


def upgrade():
    conn = op.get_bind()
    input_params = {
        "sms_sender_id": SMS_SENDER_ID,
        "inbound_number": INBOUND_NUMBER,
        "notify_service_id": NOTIFY_SERVICE_ID
    }
    conn.execute(text("INSERT INTO service_sms_senders (id, sms_sender, service_id, is_default, created_at) "
               "VALUES (:sms_sender_id, :inbound_number, :notify_service_id,false, now())"), input_params)


    inbound_number_id = uuid.uuid4()
    input_params = {
        "inbound_number_id": inbound_number_id,
        "inbound_number": INBOUND_NUMBER,
    }
    # by adding a row in inbound_number we ensure the number isn't added to the table and assigned to a service.
    conn.execute(text("INSERT INTO INBOUND_NUMBERS (id, number, provider, active, created_at) VALUES(:inbound_number_id, "
               ":inbound_number, 'mmg', false, now())"), input_params)


def downgrade():
    conn = op.get_bind()
    input_params = {
        "sms_sender_id": SMS_SENDER_ID
    }
    conn.execute(text("delete from service_sms_senders where id = :sms_sender_id"), input_params)
    input_params = {
        "inbound_number": INBOUND_NUMBER
    }
    conn.execute(text("delete from inbound_numbers where number = :inbound_number"), input_params)
