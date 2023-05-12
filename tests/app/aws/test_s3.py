from datetime import datetime
from os import getenv

from app.aws.s3 import delete_incomplete_uploads, get_s3_file

default_access_key = getenv('CSV_AWS_ACCESS_KEY_ID')
default_secret_key = getenv('CSV_AWS_SECRET_ACCESS_KEY')
default_region = getenv('CSV_AWS_REGION')


def single_s3_object_stub(key='foo', last_modified=None):
    return {
        'ETag': '"d41d8cd98f00b204e9800998ecf8427e"',
        'Key': key,
        'LastModified': last_modified or datetime.utcnow(),
    }


def test_get_s3_file_makes_correct_call(notify_api, mocker):
    get_s3_mock = mocker.patch('app.aws.s3.get_s3_object')
    get_s3_file('foo-bucket', 'bar-file.txt', default_access_key, default_secret_key, default_region)

    get_s3_mock.assert_called_with(
        'foo-bucket',
        'bar-file.txt',
        default_access_key,
        default_secret_key,
        default_region,
    )


def test_delete_incomplete_uploads(mocker):
    get_s3_client = mocker.patch('app.aws.s3._get_s3_client')
    get_s3_credentials = mocker.patch('app.aws.s3._s3_credentials_from_env')
    get_s3_credentials.return_value = {
        "bucket": "mybucket",
        "access_key_id": "myaccesskey",
        "secret_access_key": "mysecret",
        "region": "myregion"
    }
    get_s3_client.return_value.list_multipart_uploads.return_value = {
        'Uploads': [
            {
                'Initiated': datetime(2023, 1, 1, 12, 0, 0),
                'UploadId': 'aaa',
                'Key': 'mykey'
            }
        ]
    }
    delete_incomplete_uploads()
    get_s3_client.assert_called_once_with()
    get_s3_client.return_value.list_multipart_uploads.assert_called_once_with(Bucket="mybucket")
    get_s3_client.return_value.abort_multipart_upload.assert_called_once_with(
        Bucket="mybucket", Key="mykey", UploadId="aaa")
