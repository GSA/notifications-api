import os
import uuid

from flask import current_app, g, request
from sqlalchemy.orm.exc import NoResultFound

from app.serialised_models import SerialisedService
from notifications_python_client.authentication import (
    decode_jwt_token,
    get_token_issuer,
)
from notifications_python_client.errors import (
    TokenAlgorithmError,
    TokenDecodeError,
    TokenError,
    TokenExpiredError,
    TokenIssuerError,
)
from notifications_utils import request_helper

# stvnrlly - this is silly, but bandit has a multiline string bug (https://github.com/PyCQA/bandit/issues/658)
# and flake8 wants a multiline quote here. TODO: check on bug status and restore sanity once possible
TOKEN_MESSAGE_ONE = (
    "Invalid token: make sure your API token matches the example "  # nosec B105
)
TOKEN_MESSAGE_TWO = "at https://docs.notifications.service.gov.uk/rest-api.html#authorisation-header"  # nosec B105
GENERAL_TOKEN_ERROR_MESSAGE = TOKEN_MESSAGE_ONE + TOKEN_MESSAGE_TWO


class AuthError(Exception):
    def __init__(self, message, code, service_id=None, api_key_id=None):
        super().__init__(message, code, service_id, api_key_id)
        self.message = {"token": [message]}
        self.short_message = message
        self.code = code
        self.service_id = service_id
        self.api_key_id = api_key_id

    def __str__(self):
        return "AuthError({message}, {code}, service_id={service_id}, api_key_id={api_key_id})".format(
            **self.__dict__
        )

    def to_dict_v2(self):
        return {
            "status_code": self.code,
            "errors": [{"error": "AuthError", "message": self.short_message}],
        }


class InternalApiKey:
    def __init__(self, client_id, secret):
        self.secret = secret
        self.id = client_id
        self.expiry_date = None


def requires_no_auth():
    pass


def requires_admin_auth():
    requires_internal_auth(current_app.config.get("ADMIN_CLIENT_ID"))


def requires_internal_auth(expected_client_id):

    # Looks like we are hitting this for some reason
    # expected_client_id looks like ADMIN_CLIENT_USERNAME on the admin side, and
    # INTERNAL_CLIENT_API_KEYS is a dict
    keys = current_app.config.get("INTERNAL_CLIENT_API_KEYS")
    if keys.get(expected_client_id) is None:
        err_msg = "Unknown client_id for internal auth"
        current_app.logger.error(err_msg)
        raise TypeError(err_msg)

    request_helper.check_proxy_header_before_request()
    auth_token = _get_auth_token(request)
    client_id = _get_token_issuer(auth_token)
    if client_id != expected_client_id:
        current_app.logger.info("client_id: %s", client_id)
        current_app.logger.info("expected_client_id: %s", expected_client_id)
        err_msg = "Unauthorized: not allowed to perform this action"
        current_app.logger.error(err_msg)
        raise AuthError(err_msg, 401)

    api_keys = [
        InternalApiKey(client_id, secret)
        for secret in current_app.config.get("INTERNAL_CLIENT_API_KEYS")[client_id]
    ]

    _decode_jwt_token(auth_token, api_keys, client_id)
    g.service_id = client_id


def requires_auth():
    request_helper.check_proxy_header_before_request()

    auth_token = _get_auth_token(request)
    issuer = _get_token_issuer(
        auth_token
    )  # ie the `iss` claim which should be a service ID

    try:
        service_id = uuid.UUID(issuer)
    except Exception:
        raise AuthError("Invalid token: service id is not the right data type", 403)

    try:
        service = SerialisedService.from_id(service_id)
    except NoResultFound:
        raise AuthError("Invalid token: service not found", 403)

    if not service.api_keys:
        raise AuthError(
            "Invalid token: service has no API keys", 403, service_id=service.id
        )

    if not service.active:
        raise AuthError(
            "Invalid token: service is archived", 403, service_id=service.id
        )

    api_key = _decode_jwt_token(auth_token, service.api_keys, service.id)

    current_app.logger.info(
        "API authorised for service {} with api key {}, using issuer {} for URL: {}".format(
            service_id, api_key.id, request.headers.get("User-Agent"), request.base_url
        )
    )

    g.api_user = api_key
    g.service_id = service_id
    g.authenticated_service = service


def _decode_jwt_token(auth_token, api_keys, service_id=None):
    # Temporary expedient to get e2e tests working.  If we are in
    # the development or staging environments, just return the first
    # api key.
    if os.getenv("NOTIFY_ENVIRONMENT") in ["development", "staging"]:
        for api_key in api_keys:
            return api_key

    for api_key in api_keys:
        try:
            decode_jwt_token(auth_token, api_key.secret)
        except TypeError:
            err_msg = "Invalid token: type error"
            current_app.logger.exception(err_msg)
            raise AuthError(
                "Invalid token: type error",
                403,
                service_id=service_id,
                api_key_id=api_key.id,
            )
        except TokenExpiredError:
            if not current_app.config.get("ALLOW_EXPIRED_API_TOKEN", False):
                err_msg = (
                    "Error: Your system clock must be accurate to within 30 seconds"
                )
                current_app.logger.exception(err_msg)
                raise AuthError(
                    err_msg, 403, service_id=service_id, api_key_id=api_key.id
                )
        except TokenAlgorithmError:
            err_msg = "Invalid token: algorithm used is not HS256"
            current_app.logger.exception(err_msg)
            raise AuthError(err_msg, 403, service_id=service_id, api_key_id=api_key.id)
        except TokenDecodeError:
            # we attempted to validate the token but it failed meaning it was not signed using this api key.
            # Let's try the next one
            # TODO: Change this so it doesn't also catch `TokenIssuerError` or `TokenIssuedAtError` exceptions (which
            # are children of `TokenDecodeError`) as these should cause an auth error immediately rather than
            # continue on to check the next API key
            current_app.logger.exception(
                "TokenDecodeError. Couldn't decode auth token for given api key"
            )
            continue
        except TokenError:
            current_app.logger.exception("TokenError")
            # General error when trying to decode and validate the token
            raise AuthError(
                GENERAL_TOKEN_ERROR_MESSAGE,
                403,
                service_id=service_id,
                api_key_id=api_key.id,
            )

        if api_key.expiry_date:
            err_msg = "Invalid token: API key revoked"
            current_app.logger.error(err_msg, exc_info=True)
            raise AuthError(
                err_msg,
                403,
                service_id=service_id,
                api_key_id=api_key.id,
            )

        return api_key
    else:
        # service has API keys, but none matching the one the user provided
        # if we get here, we probably hit TokenDecodeErrors earlier
        err_msg = "Invalid token: API key not found"
        current_app.logger.error(err_msg, exc_info=True)
        raise AuthError(err_msg, 403, service_id=service_id)


def _get_auth_token(req):
    auth_header = req.headers.get("Authorization", None)
    if not auth_header:
        raise AuthError("Unauthorized: authentication token must be provided", 401)

    auth_scheme = auth_header[:7].title()

    if auth_scheme != "Bearer ":
        raise AuthError("Unauthorized: authentication bearer scheme must be used", 401)

    return auth_header[7:]


def _get_token_issuer(auth_token):
    try:
        issuer = get_token_issuer(auth_token)
    except TokenIssuerError:
        raise AuthError("Invalid token: iss field not provided", 403)
    except TokenDecodeError:
        raise AuthError(GENERAL_TOKEN_ERROR_MESSAGE, 403)
    return issuer
