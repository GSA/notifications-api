import requests
from flask import current_app


class AntivirusError(Exception):
    def __init__(self, message=None, status_code=None):
        super().__init__(message, status_code)
        self.message = message
        self.status_code = status_code

    @classmethod
    def from_exception(cls, e):
        try:
            message = e.response.json()["error"]
            status_code = e.response.status_code
        except (TypeError, ValueError, AttributeError, KeyError):
            message = "connection error"
            status_code = 503

        return cls(message, status_code)


class AntivirusClient:
    def __init__(self, api_host=None, auth_token=None):
        self.api_host = api_host
        self.auth_token = auth_token

    def init_app(self, app):
        self.api_host = app.config["ANTIVIRUS_API_HOST"]
        self.auth_token = app.config["ANTIVIRUS_API_KEY"]

    def scan(self, document_stream):
        try:
            response = requests.post(
                "{}/scan".format(self.api_host),
                headers={
                    "Authorization": "Bearer {}".format(self.auth_token),
                },
                files={"document": document_stream},
            )

            response.raise_for_status()

        except requests.RequestException as e:
            error = AntivirusError.from_exception(e)
            current_app.logger.warning(
                "Notify Antivirus API request failed with error: {}".format(
                    error.message
                )
            )

            raise error
        finally:
            document_stream.seek(0)

        return response.json()["ok"]
