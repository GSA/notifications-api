from app.utils import utc_now

from .request_cache import RequestCache  # noqa: F401 (unused import)


def total_limit_cache_key(service_id):
    return "{}-{}-{}".format(
        str(service_id), utc_now().strftime("%Y-%m-%d"), "total-count"
    )


def rate_limit_cache_key(service_id, api_key_type):
    return "{}-{}".format(str(service_id), api_key_type)
