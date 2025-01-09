from urllib.parse import parse_qs

import botocore
import pytest

from notifications_utils.s3 import S3ObjectNotFound, s3download, s3upload

contents = "some file data"
region = "eu-west-1"
bucket = "some_bucket"
location = "some_file_location"
content_type = "binary/octet-stream"


def test_s3upload_save_file_to_bucket(mocker):

    mock_s3_client = mocker.Mock()
    mocked = mocker.patch(
        "notification_utils.s3.get_s3_client", return_value=mock_s3_client
    )
    s3upload(
        filedata=contents, region=region, bucket_name=bucket, file_location=location
    )
    mocked_put = mocked.return_value.Object.return_value.put
    mocked_put.assert_called_once_with(
        Body=contents,
        ServerSideEncryption="AES256",
        ContentType=content_type,
    )


def test_s3upload_save_file_to_bucket_with_contenttype(mocker):
    content_type = "image/png"

    mock_s3_client = mocker.Mock()
    mocked = mocker.patch("app.aws.s3.get_s3_client", return_value=mock_s3_client)
    s3upload(
        filedata=contents,
        region=region,
        bucket_name=bucket,
        file_location=location,
        content_type=content_type,
    )
    mocked_put = mocked.return_value.Object.return_value.put
    mocked_put.assert_called_once_with(
        Body=contents,
        ServerSideEncryption="AES256",
        ContentType=content_type,
    )


def test_s3upload_raises_exception(app, mocker):

    mock_s3_client = mocker.Mock()
    mocked = mocker.patch("app.aws.s3.get_s3_client", return_value=mock_s3_client)
    response = {"Error": {"Code": 500}}
    exception = botocore.exceptions.ClientError(response, "Bad exception")
    mocked.return_value.Object.return_value.put.side_effect = exception
    with pytest.raises(botocore.exceptions.ClientError):
        s3upload(
            filedata=contents,
            region=region,
            bucket_name=bucket,
            file_location="location",
        )


def test_s3upload_save_file_to_bucket_with_urlencoded_tags(mocker):
    mocked = mocker.patch("notifications_utils.s3.Session.resource")
    s3upload(
        filedata=contents,
        region=region,
        bucket_name=bucket,
        file_location=location,
        tags={"a": "1/2", "b": "x y"},
    )
    mocked_put = mocked.return_value.Object.return_value.put

    # make sure tags were a urlencoded query string
    encoded_tags = mocked_put.call_args[1]["Tagging"]
    assert parse_qs(encoded_tags) == {"a": ["1/2"], "b": ["x y"]}


def test_s3upload_save_file_to_bucket_with_metadata(mocker):
    mocked = mocker.patch("notifications_utils.s3.Session.resource")
    s3upload(
        filedata=contents,
        region=region,
        bucket_name=bucket,
        file_location=location,
        metadata={"status": "valid", "pages": "5"},
    )
    mocked_put = mocked.return_value.Object.return_value.put

    metadata = mocked_put.call_args[1]["Metadata"]
    assert metadata == {"status": "valid", "pages": "5"}


def test_s3download_gets_file(mocker):
    mocked = mocker.patch("notifications_utils.s3.Session.resource")
    mocked_object = mocked.return_value.Object
    mocked_get = mocked.return_value.Object.return_value.get
    s3download("bucket", "location.file")
    mocked_object.assert_called_once_with("bucket", "location.file")
    mocked_get.assert_called_once_with()


def test_s3download_raises_on_error(mocker):
    mocked = mocker.patch("notifications_utils.s3.Session.resource")
    mocked.return_value.Object.side_effect = botocore.exceptions.ClientError(
        {"Error": {"Code": 404}},
        "Bad exception",
    )

    with pytest.raises(S3ObjectNotFound):
        s3download("bucket", "location.file")
