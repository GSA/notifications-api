import os
import re
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, url_for
from sqlalchemy import func

from notifications_utils.template import HTMLEmailTemplate, SMSMessageTemplate

DATETIME_FORMAT_NO_TIMEZONE = "%Y-%m-%d %H:%M:%S.%f"
DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
DATE_FORMAT = "%Y-%m-%d"


def pagination_links(pagination, endpoint, **kwargs):
    if "page" in kwargs:
        kwargs.pop("page", None)
    links = {}
    if pagination.has_prev:
        links["prev"] = url_for(endpoint, page=pagination.prev_num, **kwargs)
    if pagination.has_next:
        links["next"] = url_for(endpoint, page=pagination.next_num, **kwargs)
        links["last"] = url_for(endpoint, page=pagination.pages, **kwargs)
    return links


def get_prev_next_pagination_links(current_page, next_page_exists, endpoint, **kwargs):
    if "page" in kwargs:
        kwargs.pop("page", None)
    links = {}
    if current_page > 1:
        links["prev"] = url_for(endpoint, page=current_page - 1, **kwargs)
    if next_page_exists:
        links["next"] = url_for(endpoint, page=current_page + 1, **kwargs)
    return links


def url_with_token(data, url, config, base_url=None):
    from notifications_utils.url_safe_token import generate_token

    token = generate_token(data, config["SECRET_KEY"], config["DANGEROUS_SALT"])
    base_url = (base_url or config["ADMIN_BASE_URL"]) + url
    return base_url + token


def get_template_instance(template, values=None):
    from app.enums import TemplateType

    return {
        TemplateType.SMS: SMSMessageTemplate,
        TemplateType.EMAIL: HTMLEmailTemplate,
    }[template["template_type"]](template, values)


def template_model_to_dict(template):
    return {
        "id": str(template.id),
        "template_type": template.template_type,
        "content": template.content,
        "subject": getattr(template, "subject", None),
        "created_at": template.created_at,
        "name": template.name,
        "version": template.version,
    }


def get_midnight_in_utc(date):
    """
    This function converts date to midnight in UTC,
    removing the tzinfo from the datetime because the database stores the timestamps without timezone.
    :param date: the day to calculate the local midnight in UTC for
    :return: the datetime of local midnight in UTC, for example 2016-06-17 = 2016-06-16 23:00:00
    """
    return datetime.combine(date, datetime.min.time())


def get_month_from_utc_column(column):
    """
    Where queries need to count notifications by month it needs to be
    the month in local time.
    The database stores all timestamps as UTC without the timezone.
     - First set the timezone on created_at to UTC
     - then convert the timezone to local time (or America/New_York)
     - lastly truncate the datetime to month with which we can group
       queries
    """
    return func.date_trunc("month", func.timezone("UTC", func.timezone("UTC", column)))


def get_public_notify_type_text(notify_type, plural=False):
    from app.enums import NotificationType, ServicePermissionType

    notify_type_text = notify_type
    if notify_type == NotificationType.SMS:
        notify_type_text = "text message"
    elif notify_type == ServicePermissionType.UPLOAD_DOCUMENT:
        notify_type_text = "document"

    return "{}{}".format(notify_type_text, "s" if plural else "")


def midnight_n_days_ago(number_of_days):
    """
    Returns midnight a number of days ago. Takes care of daylight savings etc.
    """
    return get_midnight_in_utc(utc_now() - timedelta(days=number_of_days))


def escape_special_characters(string):
    for special_character in ("\\", "_", "%", "/"):
        string = string.replace(special_character, r"\{}".format(special_character))
    return string


def get_archived_db_column_value(column):
    date = utc_now().strftime("%Y-%m-%d")
    return f"_archived_{date}_{column}"


def get_dt_string_or_none(val):
    return val.strftime(DATETIME_FORMAT) if val else None


# Function used for debugging.
# Do print(hilite(message)) while debugging, then remove your print statements
def hilite(message):
    ansi_green = "\033[32m"
    ansi_reset = "\033[0m"
    return f"{ansi_green}{message}{ansi_reset}"


def aware_utcnow():
    return datetime.now(timezone.utc)


def naive_utcnow():
    return aware_utcnow().replace(tzinfo=None)


def utc_now():
    return naive_utcnow()


def debug_not_production(msg):
    if os.getenv("NOTIFY_ENVIRONMENT") not in ["production"]:
        current_app.logger.info(msg)


def is_suspicious_input(input_str):
    if not isinstance(input_str, str):
        return False

    pattern = re.compile(
        r"""
                         (?i) # case insensite
                         \b  # word boundary
                         ( # start of group for SQL keywords
                         OR   # match SQL keyword OR
                         |AND
                         |UNION
                         |SELECT
                         |DROP
                         |INSERT
                         |UPDATE
                         |DELETE
                         |EXEC
                         |TRUNCATE
                         |CREATE
                         |ALTER
                         |-- # match SQL single-line comment
                         |/\* # match SQL multi-line comment
                         |\bpg_sleep\b # Match PostgreSQL 'pg_sleep' function

                         |\bsleep\b # Match SQL Server 'sleep' function
                         ) # End SQL keywords and function group
                         | # OR operator to include an alternate pattern
                         [';]{2,} # Match two or more consecutive single quotes or semi-colons
                         """,
        re.VERBOSE,
    )
    return bool(re.search(pattern, input_str))


def is_valid_id(id):
    if not isinstance(id, str):
        return True
    return bool(re.match(r"^[a-zA-Z0-9_-]{1,50}$", id))


def check_suspicious_id(*args):
    for id in args:
        if not is_valid_id(id):
            abort(403)
        if is_suspicious_input(id):
            abort(403)
