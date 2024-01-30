"""empty message

Revision ID: 0082_add_go_live_template
Revises: 0081_noti_status_as_enum
Create Date: 2017-05-10 16:06:04.070874

"""

# revision identifiers, used by Alembic.
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from flask import current_app
from sqlalchemy import text

revision = "0082_add_go_live_template"
down_revision = "0081_noti_status_as_enum"

template_id = "618185c6-3636-49cd-b7d2-6f6f5eb3bdde"


def upgrade():
    template_insert = """
        INSERT INTO templates (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False, :notify_service_id, :subject, :user_id, 1, :process_type)
    """
    template_history_insert = """
        INSERT INTO templates_history (id, name, template_type, created_at, content, archived, service_id, subject, created_by_id, version, process_type)
        VALUES (:template_id, :template_name, :template_type, :time_now, :content, False, :notify_service_id, :subject, :user_id, 1, :process_type)
    """

    template_content = """Hi ((name)),

((service name)) is now live on GOV.UK Notify.

You can send up to ((message limit)) messages per day.

As a live service, you’ll need to know who to contact if you have a question, or something goes wrong.

^To get email updates whenever there is a problem with Notify, it’s important that you subscribe to our system status page:
https://status.notifications.service.gov.uk

If our system status page shows a problem, then we’ve been alerted and are working on it – you don’t need to contact us.
#Problems or questions during office hours

Our office hours are 9.30am to 5.30pm, Monday to Friday.

To report a problem or ask a question, go to the support page:
https://www.notifications.service.gov.uk/support

We’ll reply within 30 minutes whether you’re reporting a problem or just asking a question.

The team are also available to answer questions on the cross-government Slack channel:
https://ukgovernmentdigital.slack.com/messages/govuk-notify

#Problems or questions out of hours

We offer out of hours support for emergencies.

It’s only an emergency if:
*   no one in your team can log in
*   a ‘technical difficulties’ error appears when you try to upload a file
*   a 500 response code appears when you try to send messages using the API

If you have one of these emergencies, email details to:
testsender@dispostable.com

^Only use this email address for out of hours emergencies. Don’t share this address with people outside of your team.

We’ll get back to you within 30 minutes and give you hourly updates until the problem’s fixed.

For non-emergency problems or questions, use our support page and we’ll reply in office hours:
https://www.notifications.service.gov.uk/support
#Escalation for emergency problems

If we haven’t acknowledged an emergency problem you’ve reported within 30 minutes and you need to know what’s happening, you can escalate to:

or

Thanks
GOV.UK Notify team
"""

    template_name = "Automated \"You''re now live\" message"
    template_subject = "((service name)) is now live on GOV.UK Notify"

    input_params = {
        "template_id": template_id,
        "template_name": template_name,
        "template_type": "email",
        "time_now": datetime.utcnow(),
        "content": template_content,
        "notify_service_id": current_app.config["NOTIFY_SERVICE_ID"],
        "subject": template_subject,
        "user_id": current_app.config["NOTIFY_USER_ID"],
        "process_type": "normal",
    }
    conn = op.get_bind()
    conn.execute(text(template_history_insert), input_params)

    conn.execute(text(template_insert), input_params)


def downgrade():
    input_params = {"template_id": template_id}
    conn = op.get_bind()
    conn.execute(
        text("DELETE FROM notifications WHERE template_id = '{}'"), input_params
    )
    conn.execute(
        text("DELETE FROM notification_history WHERE template_id = '{}'"), input_params
    )
    conn.execute(text("DELETE FROM templates_history WHERE id = '{}'"), input_params)
    conn.execute(text("DELETE FROM templates WHERE id = '{}'"), input_params)
