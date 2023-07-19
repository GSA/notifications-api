"""

Revision ID: 0391_update_sms_numbers
Revises: 0390_drop_dvla_provider
Create Date: 2023-03-01 12:36:38.226954

"""
from alembic import op
from flask import current_app
import sqlalchemy as sa


revision = '0391_update_sms_numbers'
down_revision = '0390_drop_dvla_provider'
OLD_SMS_NUMBER = "18446120782"
NEW_SMS_NUMBER = current_app.config['NOTIFY_INTERNATIONAL_SMS_SENDER'].strip('+')


def upgrade():
    op.alter_column("service_sms_senders", "sms_sender", type_=sa.types.String(length=255))
    op.alter_column("inbound_numbers", "number", type_=sa.types.String(length=255))
    op.execute(f"UPDATE service_sms_senders SET sms_sender = '+{NEW_SMS_NUMBER}' WHERE sms_sender IN ('{OLD_SMS_NUMBER}', '{NEW_SMS_NUMBER}')")
    op.execute(f"UPDATE inbound_numbers SET number = '+{NEW_SMS_NUMBER}' WHERE number IN ('{OLD_SMS_NUMBER}', '{NEW_SMS_NUMBER}')")



def downgrade():
    op.execute(f"UPDATE service_sms_senders SET sms_sender = '{OLD_SMS_NUMBER}' WHERE sms_sender = '+{NEW_SMS_NUMBER}'")
    op.execute(f"UPDATE inbound_numbers SET number = '{OLD_SMS_NUMBER}' WHERE number = '+{NEW_SMS_NUMBER}'")
    op.alter_column("service_sms_senders", "sms_sender", type_=sa.types.String(length=11))
    op.alter_column("inbound_numbers", "number", type_=sa.types.String(length=11))
