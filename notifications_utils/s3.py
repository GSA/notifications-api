import urllib

import botocore
from boto3 import Session
from botocore.config import Config
from flask import current_app

from app.config import _s3_credentials_from_env
from app.utils import hilite

AWS_CLIENT_CONFIG = Config(
    # This config is required to enable S3 to connect to FIPS-enabled
    # endpoints.  See https://aws.amazon.com/compliance/fips/ for more
    # information.
    s3={
        "addressing_style": "virtual",
    },
    max_pool_connections=50,
    use_fips_endpoint=True,
)
default_regions = "us-gov-west-1"


def get_s3_resource():

    credentials = _s3_credentials_from_env("CSV")
    current_app.logger.info(hilite(f"CREDENTIALS {credentials}"))
    session = Session(
        aws_access_key_id=credentials["access_key_id"],
        aws_secret_access_key=credentials["secret_access_key"],
        region_name=credentials["region"],
    )
    noti_s3_resource = session.resource("s3", config=AWS_CLIENT_CONFIG)
    return noti_s3_resource


def s3upload(
    filedata,
    region,
    bucket_name,
    file_location,
    content_type="binary/octet-stream",
    tags=None,
    metadata=None,
):
    _s3 = get_s3_resource()

    key = _s3.Object(bucket_name, file_location)

    put_args = {
        "Body": filedata,
        "ServerSideEncryption": "AES256",
        "ContentType": content_type,
    }

    if tags:
        tags = urllib.parse.urlencode(tags)
        put_args["Tagging"] = tags

    if metadata:
        metadata = put_args["Metadata"] = metadata

    try:
        current_app.logger.info(f"Going to try to upload this {key}")
        key.put(**put_args)
    except botocore.exceptions.NoCredentialsError as e:
        current_app.logger.exception(
            f"Unable to upload {key} to S3 bucket because of {e}"
        )
        raise e
    except botocore.exceptions.ClientError as e:
        current_app.logger.exception(
            f"Unable to upload {key}to S3 bucket because of {e}"
        )
        raise e


class S3ObjectNotFound(botocore.exceptions.ClientError):
    pass


def s3download(
    bucket_name,
    filename,
):
    try:
        s3 = get_s3_resource()
        key = s3.Object(bucket_name, filename)
        return key.get()["Body"]
    except botocore.exceptions.ClientError as error:
        raise S3ObjectNotFound(error.response, error.operation_name)
