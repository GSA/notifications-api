"""empty message

Revision ID: 0377_add_inbound_sms_number
Revises: 0376_add_provider_response
Create Date: 2022-09-30 11:04:15.888017

"""
import uuid

from alembic import op
from flask import current_app


revision = '0377_add_inbound_sms_number'
down_revision = '0376_add_provider_response'

INBOUND_NUMBER_ID = '9b5bc009-b847-4b1f-8a54-f3b5f95cff18'
INBOUND_NUMBER = current_app.config['NOTIFY_INTERNATIONAL_SMS_SENDER'].strip('+')
DEFAULT_SERVICE_ID = current_app.config['NOTIFY_SERVICE_ID']

def upgrade():
    op.get_bind()

    # delete the previous inbound_number with mmg as provider
    table_name = 'inbound_numbers'
    select_by_col = 'number'
    select_by_val = INBOUND_NUMBER
    op.execute(f"delete from {table_name} where {select_by_col} = '{select_by_val}'")

    # add the inbound number for the default service to inbound_numbers
    table_name = 'inbound_numbers'
    provider = 'sns'
    active = 'true'
    op.execute(f"insert into {table_name} (id, number, provider, service_id, active, created_at) VALUES('{INBOUND_NUMBER_ID}', '{INBOUND_NUMBER}', '{provider}','{DEFAULT_SERVICE_ID}', '{active}', 'now()')")

    # add the inbound number for the default service to service_sms_senders
    table_name = 'service_sms_senders'
    sms_sender = INBOUND_NUMBER
    select_by_col = 'id'
    select_by_val = '286d6176-adbe-7ea7-ba26-b7606ee5e2a4'
    op.execute(f"update {table_name} set {'sms_sender'}='{sms_sender}' where {select_by_col} = '{select_by_val}'")

    # add the inbound number for the default service to inbound_numbers
    table_name = 'service_permissions'
    permission = 'inbound_sms'
    active = 'true'
    op.execute(f"insert into {table_name} (service_id, permission, created_at) VALUES('{DEFAULT_SERVICE_ID}', '{permission}', 'now()')")
    # pass


def downgrade():
    delete_sms_sender = f"delete from service_sms_senders where inbound_number_id = '{INBOUND_NUMBER_ID}'"
    delete_inbound_number = f"delete from inbound_numbers where number = '{INBOUND_NUMBER}'"
    delete_service_inbound_permission = f"delete from service_permissions where service_id = '{DEFAULT_SERVICE_ID}' and permission = 'inbound_sms'"
    recreate_mmg_inbound_number = f"insert into inbound_numbers (id, number, provider, service_id, active, created_at) VALUES('d7aea27f-340b-4428-9b20-4470dd978bda', '{INBOUND_NUMBER}', 'mmg', 'null', 'false', 'now()')"
    op.execute(delete_sms_sender)
    op.execute(delete_inbound_number)
    op.execute(delete_service_inbound_permission)
    op.execute(recreate_mmg_inbound_number)
    # pass
