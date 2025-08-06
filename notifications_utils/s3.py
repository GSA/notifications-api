import botocore
from boto3 import Session
from botocore.config import Config
from flask import current_app

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
    access_key = current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"]
    secret_key = current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"]
    region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]
    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    s3_resource = session.resource("s3", config=AWS_CLIENT_CONFIG)
    return s3_resource


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
