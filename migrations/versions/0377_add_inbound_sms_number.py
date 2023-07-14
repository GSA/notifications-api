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
    # table_name = 'inbound_numbers'
    # select_by_col = 'number'
    # select_by_val = INBOUND_NUMBER
    op.execute("delete from inbound_numbers where number = '{}'".format(INBOUND_NUMBER))

    # add the inbound number for the default service to inbound_numbers
    op.execute("insert into inbound_numbers "
               "(id, number, provider, service_id, active, created_at) "
               "VALUES ('{}', '{}', 'sns', '{}', 'true', now())".format(INBOUND_NUMBER_ID,
                                                                        INBOUND_NUMBER, DEFAULT_SERVICE_ID))

    # add the inbound number for the default service to service_sms_senders
    op.execute("update service_sms_senders set sms_sender='{}' "
               "where id = '286d6176-adbe-7ea7-ba26-b7606ee5e2a4'".format(INBOUND_NUMBER))

    # add the inbound number for the default service to inbound_numbers
    op.execute("insert into service_permissions (service_id, permission, created_at) "
               "VALUES('{}', 'inbound_sms', now())".format(DEFAULT_SERVICE_ID))
    # pass


def downgrade():
    op.execute("delete from service_sms_senders where inbound_number_id = '{}'".format(INBOUND_NUMBER_ID))
    op.execute("delete from inbound_numbers where number = '{}'".format(INBOUND_NUMBER))
    op.execute("delete from service_permissions where service_id = '{}' and permission = 'inbound_sms'".format(
        DEFAULT_SERVICE_ID))
    op.execute("insert into inbound_numbers (id, number, provider, service_id, active, created_at) "
               "VALUES('d7aea27f-340b-4428-9b20-4470dd978bda', '{}', 'mmg', 'null', 'false', 'now()')".format(
        INBOUND_NUMBER))
    # pass
