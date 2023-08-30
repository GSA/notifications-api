import json
import os

import pytest

from app.cloudfoundry_config import CloudfoundryConfig

_bucket_credentials = {
    "access_key_id": "csv-access",
    "bucket": "csv-upload-bucket",
    "region": "us-gov-west-1",
    "secret_access_key": "csv-secret",
}
_postgres_url = "postgres://postgres:password@localhost:5432/db_name"


@pytest.fixture
def vcap_services():
    return {
        "aws-rds": [{"credentials": {"uri": _postgres_url}}],
        "aws-elasticache-redis": [{"credentials": {"uri": "redis://xxx:6379"}}],
        "s3": [
            {
                "name": "notify-api-csv-upload-bucket-test",
                "credentials": _bucket_credentials,
            },
            {
                "name": "notify-api-contact-list-bucket-test",
                "credentials": {
                    "access_key_id": "contact-access",
                    "bucket": "contact-list-bucket",
                    "region": "us-gov-west-1",
                    "secret_access_key": "contact-secret",
                },
            },
        ],
        "user-provided": [],
    }


def test_database_url(vcap_services):
    os.environ["DATABASE_URL"] = _postgres_url

    assert (
        CloudfoundryConfig().database_url
        == "postgresql://postgres:password@localhost:5432/db_name"
    )


def test_redis_url(vcap_services):
    os.environ["VCAP_SERVICES"] = json.dumps(vcap_services)

    assert CloudfoundryConfig().redis_url == "rediss://xxx:6379"


def test_redis_url_falls_back_to_REDIS_URL():
    expected = "redis://yyy:6379"
    os.environ["REDIS_URL"] = expected
    os.environ["VCAP_SERVICES"] = ""

    assert CloudfoundryConfig().redis_url == expected


def test_s3_bucket_credentials(vcap_services):
    os.environ["VCAP_SERVICES"] = json.dumps(vcap_services)

    assert (
        CloudfoundryConfig().s3_credentials("notify-api-csv-upload-bucket-test")
        == _bucket_credentials
    )


def test_s3_bucket_credentials_falls_back_to_empty_creds():
    os.environ["VCAP_SERVICES"] = ""
    expected = {
        "bucket": "",
        "access_key_id": "",
        "secret_access_key": "",
        "region": "",
    }

    assert CloudfoundryConfig().s3_credentials("bucket") == expected
