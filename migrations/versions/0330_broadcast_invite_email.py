"""

Revision ID: 0330_broadcast_invite_email
Revises: 0329_purge_broadcast_data
Create Date: 2020-09-15 14:17:01.963181

"""

# revision identifiers, used by Alembic.
from datetime import datetime

from alembic import op
from sqlalchemy import text

revision = '0330_broadcast_invite_email'
down_revision = '0329_purge_broadcast_data'

user_id = '6af522d0-2915-4e52-83a3-3690455a5fe6'
service_id = 'd6aa2c68-a2d9-4437-ab19-3ae8eb202553'
template_id = '46152f7c-6901-41d5-8590-a5624d0d4359'

broadcast_invitation_template_name = 'Notify broadcast invitation email'
broadcast_invitation_subject = "((user_name)) has invited you to join ((service_name)) on GOV.UK Notify"
broadcast_invitation_content = """((user_name)) has invited you to join ((service_name)) on GOV.UK Notify.

In an emergency, use Notify to broadcast an alert, warning the public about an imminent risk to life.

Use this link to join the team:
((url))

This invitation will stop working at midnight tomorrow. This is to keep ((service_name)) secure.

Thanks

GOV.​UK Notify team
https://www.gov.uk/notify
"""


def upgrade():
    insert_query_t = """
      INSERT INTO templates
      (id, name, template_type, created_at, content, archived, service_id,
      subject, created_by_id, version, process_type, hidden)
      VALUES
      (:template_id, :template_name, 'email', :time_now, :content, False, :service_id, :subject, :user_id, 1, 'normal', False)
    """

    insert_query_th = """
          INSERT INTO templates_history
          (id, name, template_type, created_at, content, archived, service_id,
          subject, created_by_id, version, process_type, hidden)
          VALUES
      (:template_id, :template_name, 'email', :time_now, :content, False, :service_id, :subject, :user_id, 1, 'normal', False)
        """
    conn = op.get_bind()

    input_params = {
        "template_id": template_id,
        "template_name": broadcast_invitation_template_name,
        "time_now": datetime.utcnow(),
        "content": broadcast_invitation_content,
        "service_id": service_id,
        "subject": broadcast_invitation_subject,
        "user_id": user_id

    }
    conn.execute(text(insert_query_t), input_params)
    conn.execute(text(insert_query_th), input_params)


def downgrade():
    conn = op.get_bind()
    input_params = {
        "template_id": template_id
    }
    conn.execute(text("delete from templates where id = :template_id"), input_params)
    conn.execute(text("delete from templates_history where id = :template_id"), input_params)
