import json
from functools import wraps

from flask import Blueprint, current_app, jsonify, request

from app.config import QueueNames
from app.notifications.utils import autoconfirm_subscription
from app.schema_validation import validate
from app.v2.errors import register_errors

letter_callback_blueprint = Blueprint('notifications_letter_callback', __name__)
register_errors(letter_callback_blueprint)


dvla_sns_callback_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "sns callback received on s3 update",
    "type": "object",
    "title": "dvla internal sns callback",
    "properties": {
        "Type": {"enum": ["Notification", "SubscriptionConfirmation"]},
        "MessageId": {"type": "string"},
        "Message": {"type": ["string", "object"]}
    },
    "required": ["Type", "MessageId", "Message"]
}


def validate_schema(schema):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kw):
            validate(request.get_json(force=True), schema)
            return f(*args, **kw)
        return wrapper
    return decorator
