from abc import abstractmethod, abstractproperty
from typing import final

from app.clients import Client, ClientException


class SmsClientResponseException(ClientException):
    """
    Base Exception for SmsClientsResponses
    """

    def __init__(self, message):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return f"Message {self.message}"


class SmsClient(Client):
    """
    Base Sms client for sending smss.
    """

    @abstractmethod
    def send_sms(self, *args, **kwargs):
        raise NotImplementedError("TODO Need to implement.")

    @abstractproperty
    def name(self):
        raise NotImplementedError("TODO Need to implement.")

    @final
    def get_name(self):
        return self.name
