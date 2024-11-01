from abc import abstractmethod
from typing import Protocol

from botocore.config import Config

from app.enums import NotificationType

AWS_CLIENT_CONFIG = Config(
    # This config is required to enable S3 to connect to FIPS-enabled
    # endpoints.  See https://aws.amazon.com/compliance/fips/ for more
    # information.
    s3={
        "addressing_style": "virtual",
    },
    use_fips_endpoint=True,
    # This is the default but just for doc sake
    # there may come a time when increasing this helps
    # with job cache management.
    # max_pool_connections=10,
    # Reducing to 4 connections due to BrokenPipeErrors
    max_pool_connections=4,
)


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
        assert notification_type in {
            NotificationType.EMAIL,
            NotificationType.SMS,
        }  # nosec B101

        if notification_type == NotificationType.EMAIL:
            return self.get_email_client(name)

        if notification_type == NotificationType.SMS:
            return self.get_sms_client(name)
