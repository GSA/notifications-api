from abc import abstractmethod
from typing import Protocol

from app.models import NotificationType
from botocore.config import Config

AWS_CLIENT_CONFIG = Config(
    # This config is required to enable S3 to connect to FIPS-enabled
    # endpoints.  See https://aws.amazon.com/compliance/fips/ for more
    # information.
    s3={
        "addressing_style": "virtual",
    },
    use_fips_endpoint=True,
)
STATISTICS_REQUESTED = "requested"
STATISTICS_DELIVERED = "delivered"
STATISTICS_FAILURE = "failure"


class ClientException(Exception):
    """
    Base Exceptions for sending notifications that fail
    """

    pass


class Client(Protocol):
    """
    Base client for sending notifications.
    """

    @abstractmethod
    def init_app(self, current_app, *args, **kwargs):
        raise NotImplementedError("TODO: Need to implement.")


class NotificationProviderClients(object):
    sms_clients = {}
    email_clients = {}

    def init_app(self, sms_clients, email_clients):
        for client in sms_clients:
            self.sms_clients[client.name] = client

        for client in email_clients:
            self.email_clients[client.name] = client

    def get_sms_client(self, name):
        return self.sms_clients.get(name)

    def get_email_client(self, name):
        return self.email_clients.get(name)

    def get_client_by_name_and_type(self, name, notification_type):
        assert notification_type in {NotificationType.EMAIL, NotificationType.SMS}  # nosec B101

        if notification_type == NotificationType.EMAIL:
            return self.get_email_client(name)

        if notification_type == NotificationType.SMS:
            return self.get_sms_client(name)
