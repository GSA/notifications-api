import requests
from flask import current_app


class ZendeskError(Exception):
    def __init__(self, response):
        super().__init__(str(response))
        self.response = response


class ZendeskClient:
    # the account used to authenticate with. If no requester is provided, the ticket will come from this account.
    NOTIFY_ZENDESK_EMAIL = "zd-api-notify@digital.cabinet-office.gov.uk"

    ZENDESK_TICKET_URL = "https://govuk.zendesk.com/api/v2/tickets.json"

    def __init__(self):
        self.api_key = None

    def init_app(self, app, *args, **kwargs):
        self.api_key = app.config.get("ZENDESK_API_KEY")

    def send_ticket_to_zendesk(self, ticket):
        response = requests.post(
            self.ZENDESK_TICKET_URL,
            json=ticket.request_data,
            auth=(f"{self.NOTIFY_ZENDESK_EMAIL}/token", self.api_key),
        )

        if response.status_code != 201:
            current_app.logger.error(
                f"Zendesk create ticket request failed with {response.status_code} '{response.json()}'"
            )
            raise ZendeskError(response)

        ticket_id = response.json()["ticket"]["id"]

        current_app.logger.info(f"Zendesk create ticket {ticket_id} succeeded")


class NotifySupportTicket:
    PRIORITY_URGENT = "urgent"
    PRIORITY_HIGH = "high"
    PRIORITY_NORMAL = "normal"
    PRIORITY_LOW = "low"

    TAGS_P2 = "govuk_notify_support"
    TAGS_P1 = "govuk_notify_emergency"

    TYPE_PROBLEM = "problem"
    TYPE_INCIDENT = "incident"
    TYPE_QUESTION = "question"
    TYPE_TASK = "task"

    # Group: 3rd Line--Notify Support
    NOTIFY_GROUP_ID = 360000036529
    # Organization: GDS
    NOTIFY_ORG_ID = 21891972
    NOTIFY_TICKET_FORM_ID = 1900000284794

    def __init__(
        self,
        subject,
        message,
        ticket_type,
        p1=False,
        user_name=None,
        user_email=None,
        requester_sees_message_content=True,
        technical_ticket=False,
        ticket_categories=None,
        org_id=None,
        org_type=None,
        service_id=None,
        email_ccs=None,
    ):
        self.subject = subject
        self.message = message
        self.ticket_type = ticket_type
        self.p1 = p1
        self.user_name = user_name
        self.user_email = user_email
        self.requester_sees_message_content = requester_sees_message_content
        self.technical_ticket = technical_ticket
        self.ticket_categories = ticket_categories or []
        self.org_id = org_id
        self.org_type = org_type
        self.service_id = service_id
        self.email_ccs = email_ccs

    @property
    def request_data(self):
        data = {
            "ticket": {
                "subject": self.subject,
                "comment": {
                    "body": self.message,
                    "public": self.requester_sees_message_content,
                },
                "group_id": self.NOTIFY_GROUP_ID,
                "organization_id": self.NOTIFY_ORG_ID,
                "ticket_form_id": self.NOTIFY_TICKET_FORM_ID,
                "priority": self.PRIORITY_URGENT if self.p1 else self.PRIORITY_NORMAL,
                "tags": [self.TAGS_P1 if self.p1 else self.TAGS_P2],
                "type": self.ticket_type,
                "custom_fields": self._get_custom_fields(),
            }
        }

        if self.email_ccs:
            data["ticket"]["email_ccs"] = [
                {"user_email": email, "action": "put"} for email in self.email_ccs
            ]

        # if no requester provided, then the call came from within Notify 👻
        if self.user_email:
            data["ticket"]["requester"] = {
                "email": self.user_email,
                "name": self.user_name or "(no name supplied)",
            }

        return data

    def _get_custom_fields(self):
        technical_ticket_tag = (
            f'notify_ticket_type_{"" if self.technical_ticket else "non_"}technical'
        )
        org_type_tag = f"notify_org_type_{self.org_type}" if self.org_type else None

        return [
            {
                "id": "1900000744994",
                "value": technical_ticket_tag,
            },  # Notify Ticket type field
            {
                "id": "360022836500",
                "value": self.ticket_categories,
            },  # Notify Ticket category field
            {
                "id": "360022943959",
                "value": self.org_id,
            },  # Notify Organisation ID field
            {
                "id": "360022943979",
                "value": org_type_tag,
            },  # Notify Organisation type field
            {
                "id": "1900000745014",
                "value": self.service_id,
            },  # Notify Service ID field
        ]
