from flask import current_app, json, jsonify
from jsonschema import ValidationError as JsonSchemaValidationError
from marshmallow import ValidationError
from sqlalchemy.exc import DataError
from sqlalchemy.orm.exc import NoResultFound

from app.authentication.auth import AuthError
from app.enums import KeyType
from app.exceptions import ArchiveValidationError
from notifications_utils.recipients import InvalidEmailError


class InvalidRequest(Exception):
    code = None
    fields = []

    def __init__(self, message, status_code):
        super().__init__(message, status_code)
        self.message = message
        self.status_code = status_code

    def to_dict(self):
        return {"result": "error", "message": self.message}

    def to_dict_v2(self):
        """
        Version 2 of the public api error response.
        """
        return {
            "status_code": self.status_code,
            "errors": [{"error": self.__class__.__name__, "message": self.message}],
        }

    def __str__(self):
        return str(self.to_dict())


# TODO maintainability what is this for?  How to unit test it?
def register_errors(blueprint):
    @blueprint.errorhandler(InvalidEmailError)
    def invalid_format(error):
        # Please not that InvalidEmailError is re-raised for InvalidEmail or InvalidPhone,
        # work should be done in the utils app to tidy up these errors.
        return jsonify(result="error", message=str(error)), 400

    @blueprint.errorhandler(AuthError)
    def authentication_error(error):
        return jsonify(result="error", message=error.message), error.code

    @blueprint.errorhandler(ValidationError)
    def marshmallow_validation_error(error):
        current_app.logger.error(error, exc_info=True)
        return jsonify(result="error", message=error.messages), 400

    @blueprint.errorhandler(JsonSchemaValidationError)
    def jsonschema_validation_error(error):
        current_app.logger.error(error, exc_info=True)
        return jsonify(json.loads(error.message)), 400

    @blueprint.errorhandler(ArchiveValidationError)
    def archive_validation_error(error):
        current_app.logger.error(error, exc_info=True)
        return jsonify(result="error", message=str(error)), 400

    @blueprint.errorhandler(InvalidRequest)
    def invalid_data(error):
        response = jsonify(error.to_dict())
        response.status_code = error.status_code
        current_app.logger.error(error, exc_info=True)
        return response

    @blueprint.errorhandler(400)
    def bad_request(e):
        msg = e.description or "Invalid request parameters"
        current_app.logger.exception(msg)
        return jsonify(result="error", message=str(msg)), 400

    @blueprint.errorhandler(401)
    def unauthorized(e):
        error_message = "Unauthorized: authentication token must be provided"
        return (
            jsonify(result="error", message=error_message),
            401,
            [("WWW-Authenticate", "Bearer")],
        )

    @blueprint.errorhandler(403)
    def forbidden(e):
        error_message = "Forbidden: invalid authentication token provided"
        return jsonify(result="error", message=error_message), 403

    @blueprint.errorhandler(429)
    def limit_exceeded(e):
        current_app.logger.exception(e)
        return jsonify(result="error", message=str(e.description)), 429

    @blueprint.errorhandler(NoResultFound)
    @blueprint.errorhandler(DataError)
    def no_result_found(e):
        current_app.logger.info(e)
        return jsonify(result="error", message="No result found"), 404

    # this must be defined after all other error handlers since it catches the generic Exception object
    @blueprint.app_errorhandler(500)
    @blueprint.errorhandler(Exception)
    def internal_server_error(e):
        # if e is a werkzeug InternalServerError then it may wrap the original exception. For more details see:
        # https://flask.palletsprojects.com/en/1.1.x/errorhandling/?highlight=internalservererror#unhandled-exceptions
        e = getattr(e, "original_exception", e)
        current_app.logger.exception(e)
        return jsonify(result="error", message="Internal server error"), 500


class TooManyRequestsError(InvalidRequest):
    status_code = 429
    message_template = "Exceeded send limits ({}) for today"

    def __init__(self, sending_limit):  # noqa: B042
        self.message = self.message_template.format(sending_limit)
        self.sending_limit = sending_limit
        super().__init__(self.message, self.status_code)


class TotalRequestsError(InvalidRequest):
    status_code = 429
    message_template = "Exceeded total application limits ({}) for today"

    def __init__(self, sending_limit):  # noqa: B042
        self.message = self.message_template.format(sending_limit)
        self.sending_limit = sending_limit
        super().__init__(self.message, self.status_code)


class RateLimitError(InvalidRequest):
    status_code = 429
    message_template = (
        "Exceeded rate limit for key type {} of {} requests per {} seconds"
    )

    def __init__(self, sending_limit, interval, key_type):  # noqa: B042
        # normal keys are spoken of as "live" in the documentation
        # so using this in the error messaging
        if key_type == KeyType.NORMAL:
            key_type = "live"

        self.message = self.message_template.format(
            key_type.upper(), sending_limit, interval
        )
        self.sending_limit = sending_limit
        self.interval = interval
        self.key_type = key_type
        super().__init__(self.message, self.status_code)


class BadRequestError(InvalidRequest):
    message = "An error occurred"

    def __init__(self, fields=None, message=None, status_code=400):  # noqa: B042
        self.fields = fields or []
        self.message = message if message else self.message
        self.status_code = status_code
        super().__init__(self.message, self.status_code)
