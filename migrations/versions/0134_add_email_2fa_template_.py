"""

Revision ID: 0134_add_email_2fa_template
Revises: 0133_set_services_sms_prefix
Create Date: 2017-11-03 13:52:59.715203

"""
from datetime import datetime

from alembic import op
from flask import current_app
from sqlalchemy import text

revision = '0134_add_email_2fa_template'
down_revision = '0133_set_services_sms_prefix'

template_id = '299726d2-dba6-42b8-8209-30e1d66ea164'


def upgrade():
    template_insert = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False, :notify_service_id, :subject, :user_id, 1,:process_type)
    """
    template_history_insert = """
        INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False, :notify_service_id, :subject, :user_id, 1,:process_type)
    """

    template_content = '\n'.join([
        'Hi ((name)),',
        '',
        'To sign in to GOV.​UK Notify please open this link:',
        '((url))',
    ])

    template_name = "Notify email verify code"
    template_subject = 'Sign in to GOV.UK Notify'

    input_params = {
        'template_id': template_id,
        'template_name': template_name,
        'template_type': 'email',
        'time_now': datetime.utcnow(),
        'content': template_content,
        'notify_service_id': current_app.config['NOTIFY_SERVICE_ID'],
        'subject': template_subject,
        'user_id': current_app.config['NOTIFY_USER_ID'],
        'process_type': 'normal'
    }
    conn = op.get_bind()

    conn.execute(
        text(template_history_insert), input_params
    )

    conn.execute(
        text(template_insert), input_params
    )


def downgrade():
    conn = op.get_bind()
    input_params = {
        'template_id': template_id
    }
    conn.execute(text("DELETE FROM notifications WHERE template_id = :template_id"), input_params)
    conn.execute(text("DELETE FROM notification_history WHERE template_id = :template_id"), input_params)
    conn.execute(text("DELETE FROM template_redacted WHERE template_id = :template_id"), input_params)
    conn.execute(text("DELETE FROM templates_history WHERE id = :template_id"), input_params)
    conn.execute(text("DELETE FROM templates WHERE id = :template_id"), input_params)
