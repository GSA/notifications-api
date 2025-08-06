from unittest.mock import MagicMock

import botocore
import pytest

from notifications_utils.s3 import (  # s3upload,
    AWS_CLIENT_CONFIG,
    S3ObjectNotFound,
    get_s3_resource,
    s3download,
)

# from urllib.parse import parse_qs


contents = "some file data"
region = "eu-west-1"
bucket = "some_bucket"
location = "some_file_location"
content_type = "binary/octet-stream"


# def test_s3upload_save_file_to_bucket(mocker):

#     mock_s3_resource = mocker.Mock()
#     mocked = mocker.patch(
#         "notifications_utils.s3.get_s3_resource", return_value=mock_s3_resource
#     )
#     s3upload(
#         filedata=contents, region=region, bucket_name=bucket, file_location=location
#     )
#     mocked_put = mocked.return_value.Object.return_value.put
#     mocked_put.assert_called_once_with(
#         Body=contents,
#         ServerSideEncryption="AES256",
#         ContentType=content_type,
#     )


# def test_s3upload_save_file_to_bucket_with_contenttype(mocker):
#     content_type = "image/png"

#     mock_s3_resource = mocker.Mock()
#     mocked = mocker.patch(
#         "notifications_utils.s3.get_s3_resource", return_value=mock_s3_resource
#     )
#     s3upload(
#         filedata=contents,
#         region=region,
#         bucket_name=bucket,
#         file_location=location,
#         content_type=content_type,
#     )
#     mocked_put = mocked.return_value.Object.return_value.put
#     mocked_put.assert_called_once_with(
#         Body=contents,
#         ServerSideEncryption="AES256",
#         ContentType=content_type,
#     )


# def test_s3upload_raises_exception(app, mocker):

#     mock_s3_resource = mocker.Mock()
#     mocked = mocker.patch(
#         "notifications_utils.s3.get_s3_resource", return_value=mock_s3_resource
#     )
#     response = {"Error": {"Code": 500}}
#     exception = botocore.exceptions.ClientError(response, "Bad exception")
#     mocked.return_value.Object.return_value.put.side_effect = exception
#     with pytest.raises(botocore.exceptions.ClientError):
#         s3upload(
#             filedata=contents,
#             region=region,
#             bucket_name=bucket,
#             file_location="location",
#         )


# def test_s3upload_save_file_to_bucket_with_urlencoded_tags(mocker):

#     mock_s3_resource = mocker.Mock()
#     mocked = mocker.patch(
#         "notifications_utils.s3.get_s3_resource", return_value=mock_s3_resource
#     )

#     s3upload(
#         filedata=contents,
#         region=region,
#         bucket_name=bucket,
#         file_location=location,
#         tags={"a": "1/2", "b": "x y"},
#     )
#     mocked_put = mocked.return_value.Object.return_value.put

#     # make sure tags were a urlencoded query string
#     encoded_tags = mocked_put.call_args[1]["Tagging"]
#     assert parse_qs(encoded_tags) == {"a": ["1/2"], "b": ["x y"]}


# def test_s3upload_save_file_to_bucket_with_metadata(mocker):

#     mock_s3_resource = mocker.Mock()
#     mocked = mocker.patch(
#         "notifications_utils.s3.get_s3_resource", return_value=mock_s3_resource
#     )

#     s3upload(
#         filedata=contents,
#         region=region,
#         bucket_name=bucket,
#         file_location=location,
#         metadata={"status": "valid", "pages": "5"},
#     )
#     mocked_put = mocked.return_value.Object.return_value.put

#     metadata = mocked_put.call_args[1]["Metadata"]
#     assert metadata == {"status": "valid", "pages": "5"}


def test_get_s3_resource(mocker):
    mock_session = mocker.patch("notifications_utils.s3.Session")
    mock_current_app = mocker.patch("notifications_utils.s3.current_app")
    sa_key = "sec"
    sa_key = f"{sa_key}ret_access_key"

    mock_current_app.config = {
        "CSV_UPLOAD_BUCKET": {
            "access_key_id": "test_access_key",
            sa_key: "test_s_key",
            "region": "us-west-100",
        }
    }
    mock_s3_resource = MagicMock()
    mock_session.return_value.resource.return_value = mock_s3_resource
    result = get_s3_resource()

    mock_session.return_value.resource.assert_called_once_with(
        "s3", config=AWS_CLIENT_CONFIG
    )
    assert result == mock_s3_resource


def test_s3download_gets_file(mocker):

    mock_s3_resource = mocker.Mock()
    mocked = mocker.patch(
        "notifications_utils.s3.get_s3_resource", return_value=mock_s3_resource
    )

    mocked_object = mocked.return_value.Object
    mocked_object.return_value.get.return_value = {"Body": mocker.Mock()}
    s3download("bucket", "location.file")
    mocked_object.assert_called_once_with("bucket", "location.file")


def test_s3download_raises_on_error(mocker):

    mock_s3_resource = mocker.Mock()
    mocked = mocker.patch(
        "notifications_utils.s3.get_s3_resource", return_value=mock_s3_resource
    )

    mocked.return_value.Object.side_effect = botocore.exceptions.ClientError(
        {"Error": {"Code": 404}},
        "Bad exception",
    )

    with pytest.raises(S3ObjectNotFound):
        s3download("bucket", "location.file")
