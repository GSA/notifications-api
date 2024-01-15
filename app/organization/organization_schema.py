from app.enums import InvitedUserStatus, OrganizationType
from app.schema_validation.definitions import uuid

post_create_organization_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST organization schema",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "active": {"type": ["boolean", "null"]},
        "organization_type": {"enum": [e.value for e in OrganizationType]},
    },
    "required": ["name", "organization_type"],
}

post_update_organization_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST organization schema",
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "active": {"type": ["boolean", "null"]},
        "organization_type": {"enum": [e.value for e in OrganizationType]},
    },
    "required": [],
}

post_link_service_to_organization_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST link service to organization schema",
    "type": "object",
    "properties": {"service_id": uuid},
    "required": ["service_id"],
}


post_create_invited_org_user_status_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST create organization invite schema",
    "type": "object",
    "properties": {
        "email_address": {"type": "string", "format": "email_address"},
        "invited_by": uuid,
        "invite_link_host": {"type": "string"},
    },
    "required": ["email_address", "invited_by"],
}


post_update_invited_org_user_status_schema = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "description": "POST update organization invite schema",
    "type": "object",
    "properties": {"status": {"enum": [e.value for e in InvitedUserStatus]}},
    "required": ["status"],
}
