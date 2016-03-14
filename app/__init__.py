import uuid
import os
import re
from flask import request, url_for
from flask import Flask, _request_ctx_stack
from flask.ext.sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from werkzeug.local import LocalProxy
from utils import logging
from app.celery.celery import NotifyCelery
from app.clients.sms.twilio import TwilioClient
from app.clients.sms.firetext import FiretextClient
from app.clients.email.aws_ses import AwsSesClient
from app.encryption import Encryption

DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"
DATE_FORMAT = "%Y-%m-%d"

db = SQLAlchemy()
ma = Marshmallow()
notify_celery = NotifyCelery()
twilio_client = TwilioClient()
firetext_client = FiretextClient()
aws_ses_client = AwsSesClient()
encryption = Encryption()

api_user = LocalProxy(lambda: _request_ctx_stack.top.api_user)


def create_app():
    application = Flask(__name__)

    application.config.from_object(os.environ['NOTIFY_API_ENVIRONMENT'])

    init_app(application)
    db.init_app(application)
    ma.init_app(application)
    init_app(application)
    logging.init_app(application)
    twilio_client.init_app(application)
    firetext_client.init_app(application)
    aws_ses_client.init_app(application.config['AWS_REGION'])
    notify_celery.init_app(application)
    encryption.init_app(application)

    from app.service.rest import service as service_blueprint
    from app.user.rest import user as user_blueprint
    from app.template.rest import template as template_blueprint
    from app.status.healthcheck import status as status_blueprint
    from app.job.rest import job as job_blueprint
    from app.notifications.rest import notifications as notifications_blueprint
    from app.invite.rest import invite as invite_blueprint
    from app.permission.rest import permission as permission_blueprint
    from app.accept_invite.rest import accept_invite
    from app.notifications_statistics.rest import notifications_statistics as notifications_statistics_blueprint

    application.register_blueprint(service_blueprint, url_prefix='/service')
    application.register_blueprint(user_blueprint, url_prefix='/user')
    application.register_blueprint(template_blueprint)
    application.register_blueprint(status_blueprint)
    application.register_blueprint(notifications_blueprint)
    application.register_blueprint(job_blueprint)
    application.register_blueprint(invite_blueprint)
    application.register_blueprint(permission_blueprint, url_prefix='/permission')
    application.register_blueprint(accept_invite, url_prefix='/invite')
    application.register_blueprint(notifications_statistics_blueprint)

    return application


def init_app(app):
    @app.before_request
    def required_authentication():
        no_auth_req = [
            url_for('status.show_status'),
            url_for('notifications.process_ses_response'),
            url_for('notifications.process_firetext_response')
        ]
        if request.path not in no_auth_req:
            from app.authentication import auth
            error = auth.requires_auth()
            if error:
                return error

    @app.after_request
    def after_request(response):
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE')
        return response


def email_safe(string):
    return "".join([
        character.lower()
        if character.isalnum() or character == "."
        else "" for character in re.sub("\s+", ".", string.strip())
    ])


def create_uuid():
    return str(uuid.uuid4())
