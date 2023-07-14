"""

Revision ID: 0391_update_sms_numbers
Revises: 0390_drop_dvla_provider.py
Create Date: 2023-03-01 12:36:38.226954

"""
from alembic import op
from flask import current_app
import sqlalchemy as sa


revision = '0391_update_sms_numbers'
down_revision = '0390_drop_dvla_provider.py'
OLD_SMS_NUMBER = "18446120782"
NEW_SMS_NUMBER = current_app.config['NOTIFY_INTERNATIONAL_SMS_SENDER'].strip('+')


def upgrade():
    op.alter_column("service_sms_senders", "sms_sender", type_=sa.types.String(length=255))
    op.alter_column("inbound_numbers", "number", type_=sa.types.String(length=255))
    op.execute("UPDATE service_sms_senders SET sms_sender = '+{}' "
               "WHERE sms_sender IN ('{}', '{}')".format(NEW_SMS_NUMBER, OLD_SMS_NUMBER, NEW_SMS_NUMBER))
    op.execute("UPDATE inbound_numbers SET number = '+{}' "
               "WHERE number IN ('{}', '{}')".format(NEW_SMS_NUMBER, OLD_SMS_NUMBER, NEW_SMS_NUMBER))


def downgrade():
    op.execute("UPDATE service_sms_senders SET sms_sender = '{}' "
               "WHERE sms_sender = '+{}'".format(OLD_SMS_NUMBER, NEW_SMS_NUMBER))
    op.execute("UPDATE inbound_numbers SET number = '{}' "
               "WHERE number = '+{}'".format(OLD_SMS_NUMBER, NEW_SMS_NUMBER))
    op.alter_column("service_sms_senders", "sms_sender", type_=sa.types.String(length=11))
    op.alter_column("inbound_numbers", "number", type_=sa.types.String(length=11))
