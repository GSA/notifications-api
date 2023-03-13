from datetime import datetime
from os import getenv

from app.aws.s3 import get_s3_file

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
