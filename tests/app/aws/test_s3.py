import os
from datetime import datetime
from os import getenv

import pytest
from botocore.exceptions import ClientError

from app.aws.s3 import (
    file_exists,
    get_phone_number_from_s3,
    get_s3_file,
    remove_csv_object,
    remove_s3_object,
)

default_access_key = getenv("CSV_AWS_ACCESS_KEY_ID")
default_secret_key = getenv("CSV_AWS_SECRET_ACCESS_KEY")
default_region = getenv("CSV_AWS_REGION")


def single_s3_object_stub(key="foo", last_modified=None):
    return {
        "ETag": '"d41d8cd98f00b204e9800998ecf8427e"',
        "Key": key,
        "LastModified": last_modified or datetime.utcnow(),
    }


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
