from app.clients import Client, ClientException


class CloudwatchClientResponseException(ClientException):
    """
    Base Exception for SmsClientsResponses
    """

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return "Message {}".format(self.message)


class CloudwatchClient(Client):
    """
    Base Cloudwatch client for checking sms.
    """

    def init_app(self, *args, **kwargs):
        raise NotImplementedError("TODO Need to implement.")

    def check_sms(self, *args, **kwargs):
        raise NotImplementedError("TODO Need to implement.")
