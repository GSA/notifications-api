from datetime import date, datetime

import pytest
import werkzeug
from freezegun import freeze_time

from app.enums import ServicePermissionType, TemplateType
from app.utils import (
    check_suspicious_id,
    get_midnight_in_utc,
    get_public_notify_type_text,
    get_template_instance,
    is_suspicious_input,
    is_valid_id,
    midnight_n_days_ago,
)
from notifications_utils.template import HTMLEmailTemplate, SMSMessageTemplate


@pytest.mark.parametrize(
    "date, expected_date",
    [
        (datetime(2016, 1, 15, 0, 30), datetime(2016, 1, 15, 0, 0)),
        (datetime(2016, 6, 15, 0, 0), datetime(2016, 6, 15, 0, 0)),
        (datetime(2016, 9, 15, 11, 59), datetime(2016, 9, 15, 0, 0)),
        # works for both dates and datetimes
        (date(2016, 1, 15), datetime(2016, 1, 15, 0, 0)),
        (date(2016, 6, 15), datetime(2016, 6, 15, 0, 0)),
    ],
)
def test_get_midnight_in_utc_returns_expected_date(date, expected_date):
    assert get_midnight_in_utc(date) == expected_date


@pytest.mark.parametrize(
    "current_time, arg, expected_datetime",
    [
        # winter
        ("2018-01-10 23:59", 1, datetime(2018, 1, 9, 0, 0)),
        ("2018-01-11 00:00", 1, datetime(2018, 1, 10, 0, 0)),
        # bst switchover at 1am 25th
        ("2018-03-25 10:00", 1, datetime(2018, 3, 24, 0, 0)),
        ("2018-03-26 10:00", 1, datetime(2018, 3, 25, 0, 0)),
        ("2018-03-27 10:00", 1, datetime(2018, 3, 26, 0, 0)),
        # summer
        ("2018-06-05 10:00", 1, datetime(2018, 6, 4, 0, 0)),
        # zero days ago
        ("2018-01-11 00:00", 0, datetime(2018, 1, 11, 0, 0)),
        ("2018-06-05 10:00", 0, datetime(2018, 6, 5, 0, 0)),
    ],
)
def test_midnight_n_days_ago(current_time, arg, expected_datetime):
    with freeze_time(current_time):
        assert midnight_n_days_ago(arg) == expected_datetime


def test_get_public_notify_type_text():
    assert (
        get_public_notify_type_text(ServicePermissionType.UPLOAD_DOCUMENT) == "document"
    )


@pytest.mark.parametrize(
    "template_type, expected_class",
    [
        (TemplateType.SMS, SMSMessageTemplate),
        (TemplateType.EMAIL, HTMLEmailTemplate),
    ],
)
def test_get_template_instance_with_none_values(template_type, expected_class):
    """Test that get_template_instance handles None values safely for both template types"""
    template = {
        "template_type": template_type,
        "id": "test-id",
        "content": "Test content",
        "subject": "Test subject" if template_type == TemplateType.EMAIL else None,
    }

    result = get_template_instance(template, values=None)
    assert isinstance(result, expected_class)

    result_default = get_template_instance(template)
    assert isinstance(result_default, expected_class)


@pytest.mark.parametrize(
    "template_type, expected_class",
    [
        (TemplateType.SMS, SMSMessageTemplate),
        (TemplateType.EMAIL, HTMLEmailTemplate),
    ],
)
def test_get_template_instance_with_actual_values(template_type, expected_class):
    """Test that get_template_instance works normally with actual values"""
    template = {
        "template_type": template_type,
        "id": "test-id",
        "content": "Hello ((name))",
        "subject": "Test subject" if template_type == TemplateType.EMAIL else None,
    }

    values = {"name": "World"}

    result = get_template_instance(template, values=values)
    assert isinstance(result, expected_class)


def test_get_template_instance_invalid_template_type():
    """Test that get_template_instance raises KeyError for invalid template types"""
    template = {
        "template_type": "INVALID_TYPE",
        "id": "test-id",
        "content": "Test content",
    }

    with pytest.raises(KeyError):
        get_template_instance(template, values=None)


@pytest.mark.parametrize(
    "template_type, values",
    [
        (TemplateType.SMS, None),
        (TemplateType.SMS, {}),
        (TemplateType.SMS, {"name": "test"}),
        (TemplateType.EMAIL, None),
        (TemplateType.EMAIL, {}),
        (TemplateType.EMAIL, {"name": "test"}),
    ],
)
def test_get_template_instance_comprehensive(template_type, values):
    """Comprehensive test covering all combinations of template types and value scenarios"""
    template = {
        "template_type": template_type,
        "id": "test-id",
        "content": (
            "Test content ((name))" if values and "name" in values else "Test content"
        ),
        "subject": "Test subject" if template_type == TemplateType.EMAIL else None,
    }

    result = get_template_instance(template, values=values)

    if template_type == TemplateType.SMS:
        assert isinstance(result, SMSMessageTemplate)
    else:
        assert isinstance(result, HTMLEmailTemplate)


def test_is_valid_id(sample_job):
    returnVal = is_valid_id(sample_job.service_id)
    assert returnVal is True

    returnVal = is_valid_id("abc pgsleep(1)")
    assert returnVal is False


def test_check_suspicious_id(sample_job):
    # This should be good
    check_suspicious_id(sample_job.id, sample_job.service_id)

    # This should be bad
    with pytest.raises(werkzeug.exceptions.Forbidden):
        check_suspicious_id(sample_job.id, "what is this???")

    # This should be good
    check_suspicious_id(sample_job.id, None)


def test_is_suspicious_input(sample_job):
    returnVal = is_suspicious_input(sample_job.id)
    assert returnVal is False

    returnVal = is_suspicious_input("1 OR pg_sleep(1)")
    assert returnVal is True
