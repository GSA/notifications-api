import os
from datetime import timedelta
from os import getenv

import pytest
from botocore.exceptions import ClientError

from app.aws.s3 import (
    cleanup_old_s3_objects,
    file_exists,
    get_job_from_s3,
    get_personalisation_from_s3,
    get_phone_number_from_s3,
    get_s3_file,
    remove_csv_object,
    remove_s3_object,
)
from app.utils import utc_now
from notifications_utils import aware_utcnow

default_access_key = getenv("CSV_AWS_ACCESS_KEY_ID")
default_secret_key = getenv("CSV_AWS_SECRET_ACCESS_KEY")
default_region = getenv("CSV_AWS_REGION")


def single_s3_object_stub(key="foo", last_modified=None):
    return {
        "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
        "Key": key,
        "LastModified": last_modified or utc_now(),
    }


def test_cleanup_old_s3_objects(mocker):
    """
    Currently we are going to delete s3 objects if they are more than 14 days old,
    because we want to delete all jobs older than 7 days, and jobs can be scheduled
    three days in advance, and on top of that we want to leave a little cushion for
    the time being.  This test shows that a 3 day old job ("B") is not deleted,
    whereas a 30 day old job ("A") is.
    """
    mocker.patch("app.aws.s3.get_bucket_name", return_value="Bucket")
    mock_s3_client = mocker.Mock()
    mocker.patch("app.aws.s3.get_s3_client", return_value=mock_s3_client)
    mock_remove_csv_object = mocker.patch("app.aws.s3.remove_csv_object")
    lastmod30 = aware_utcnow() - timedelta(days=30)
    lastmod3 = aware_utcnow() - timedelta(days=3)

    mock_s3_client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "A", "LastModified": lastmod30},
            {"Key": "B", "LastModified": lastmod3},
        ]
    }
    cleanup_old_s3_objects()
    mock_s3_client.list_objects_v2.assert_called_with(Bucket="Bucket")
    mock_remove_csv_object.assert_called_once_with("A")


def test_get_s3_file_makes_correct_call(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    get_s3_file(
        "foo-bucket",
        "bar-file.txt",
        default_access_key,
        default_secret_key,
        default_region,
    )

    get_s3_mock.assert_called_with(
        "foo-bucket",
        "bar-file.txt",
        default_access_key,
        default_secret_key,
        default_region,
    )


@pytest.mark.parametrize(
    "job, job_id, job_row_number, expected_phone_number",
    [
        ("phone number\r\n+15555555555", "aaa", 0, "15555555555"),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "bbb",
            1,
            "15552222222",
        ),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "ccc",
            0,
            "15551111111",
        ),
        (
            "Phone number,name,date,time,address,English,Spanish\r\n15553333333,Tim,10/16,2:00 PM,5678 Tom St.,no,yes",
            "ddd",
            0,
            "15553333333",
        ),
        (
            # simulate file saved with utf8withbom
            "\\ufeffPHONE NUMBER,Name\r\n5555555550,T 1\r\n5555555551,T 5,3/31/2024\r\n5555555552,T 2",
            "eee",
            2,
            "5555555552",
        ),
    ],
)
def test_get_phone_number_from_s3(
    mocker, job, job_id, job_row_number, expected_phone_number
):
    mocker.patch("app.aws.s3.redis_store")
    get_job_mock = mocker.patch("app.aws.s3.get_job_from_s3")
    get_job_mock.return_value = job
    phone_number = get_phone_number_from_s3("service_id", job_id, job_row_number)
    assert phone_number == expected_phone_number


def mock_s3_get_object_slowdown(*args, **kwargs):
    error_response = {
        "Error": {
            "Code": "SlowDown",
            "Message": "Reduce your request rate",
        }
    }
    raise ClientError(error_response, "GetObject")


def test_get_job_from_s3_exponential_backoff_on_throttling(mocker):
    # We try multiple times to retrieve the job, and if we can't we return None
    mock_get_object = mocker.patch(
        "app.aws.s3.get_s3_object", side_effect=mock_s3_get_object_slowdown
    )
    mocker.patch("app.aws.s3.file_exists", return_value=True)
    job = get_job_from_s3("service_id", "job_id")
    assert job is None
    assert mock_get_object.call_count == 4


def test_get_job_from_s3_exponential_backoff_file_not_found(mocker):
    mock_get_object = mocker.patch("app.aws.s3.get_s3_object", return_value=None)
    mocker.patch("app.aws.s3.file_exists", return_value=False)
    job = get_job_from_s3("service_id", "job_id")
    assert job is None
    assert mock_get_object.call_count == 0


@pytest.mark.parametrize(
    "job, job_id, job_row_number, expected_personalisation",
    [
        ("phone number\r\n+15555555555", "aaa", 0, {"phone number": "+15555555555"}),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "bbb",
            1,
            {
                "day of week": "tuesday",
                "favorite color": "red",
                "phone number": "+1 (555) 222-2222",
            },
        ),
        (
            "day of week,favorite color,phone number\r\nmonday,green,1.555.111.1111\r\ntuesday,red,+1 (555) 222-2222",
            "ccc",
            0,
            {
                "day of week": "monday",
                "favorite color": "green",
                "phone number": "1.555.111.1111",
            },
        ),
    ],
)
def test_get_personalisation_from_s3(
    mocker, job, job_id, job_row_number, expected_personalisation
):
    mocker.patch("app.aws.s3.redis_store")
    get_job_mock = mocker.patch("app.aws.s3.get_job_from_s3")
    get_job_mock.return_value = job
    personalisation = get_personalisation_from_s3("service_id", job_id, job_row_number)
    assert personalisation == expected_personalisation


def test_remove_csv_object(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    remove_csv_object("mykey")

    get_s3_mock.assert_called_once_with(
        os.getenv("CSV_BUCKET_NAME"),
        "mykey",
        default_access_key,
        default_secret_key,
        default_region,
    )


def test_remove_csv_object_alternate(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    remove_s3_object(
        os.getenv("CSV_BUCKET_NAME"),
        "mykey",
        default_access_key,
        default_secret_key,
        default_region,
    )

    get_s3_mock.assert_called_once_with(
        os.getenv("CSV_BUCKET_NAME"),
        "mykey",
        default_access_key,
        default_secret_key,
        default_region,
    )


def test_file_exists_true(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")

    file_exists(
        "mykey",
    )
    get_s3_mock.assert_called_once()


def test_file_exists_false(notify_api, mocker):
    get_s3_mock = mocker.patch("app.aws.s3.get_s3_object")
    error_response = {
        "Error": {"Code": 500, "Message": "bogus"},
        "ResponseMetadata": {"HTTPStatusCode": 500},
    }
    get_s3_mock.side_effect = ClientError(
        error_response=error_response, operation_name="bogus"
    )

    with pytest.raises(ClientError):
        file_exists(
            "mykey",
        )

    get_s3_mock.assert_called_once()
