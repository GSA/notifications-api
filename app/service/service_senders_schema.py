from app.schema_validation.definitions import uuid

add_service_email_reply_to_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST service email reply to address",
    "type": "object",
    "title": "Add new email reply to address for service",
    "properties": {
        "email_address": {"type": "string", "format": "email_address"},
        "is_default": {"type": "boolean"}
    },
    "required": ["email_address", "is_default"]
}


add_service_sms_sender_request = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST add service SMS sender",
    "type": "object",
    "title": "Add new SMS sender for service",
    "properties": {
        "sms_sender": {"type": "string"},
        "is_default": {"type": "boolean"},
        "inbound_number_id": uuid
    },
    "required": ["sms_sender", "is_default"]
}
