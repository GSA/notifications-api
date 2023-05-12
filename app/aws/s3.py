import datetime

import botocore
from boto3 import Session
from flask import current_app

from app.config import _s3_credentials_from_env

FILE_LOCATION_STRUCTURE = 'service-{}-notify/{}.csv'


def _get_s3_client():
    bucket = _s3_credentials_from_env('CSV')

    session = Session(
        aws_access_key_id=bucket['access_key_id'],
        aws_secret_access_key=bucket['secret_access_key'],
        region_name=bucket['region']
    )
    s3_client = session.client('s3')
    return s3_client


def delete_incomplete_uploads():
    s3_client = _get_s3_client()
    now = datetime.datetime.utcnow()
    threshold_date = now - datetime.timedelta(days=7)

    bucket = _s3_credentials_from_env('CSV')
    bucket_name = bucket['bucket']

    response = s3_client.list_multipart_uploads(Bucket=bucket_name)
    # Looks like if you actually have no multipart uploads, then the 'Uploads' key is omitted from the response.
    # I'm not sure how we can test this since trial mode has a strict limit on the number of text messages we can
    # send, which means our csvs are never multipart uploads.
    if response.get("Uploads"):
        for upload in response['Uploads']:
            upload_initiated_date = upload['Initiated']
            if upload_initiated_date < threshold_date:
                current_app.logger.info(f"Deleting incomplete upload {upload['UploadId']} for key {upload['Key']}")
                s3_client.abort_multipart_upload(Bucket=bucket_name, Key=upload['Key'], UploadId=upload['UploadId'])
    else:
        current_app.logger.warning("No multipart uploads found in bucket")


def get_s3_file(
    bucket_name, file_location, access_key, secret_key, region
):
    s3_file = get_s3_object(bucket_name, file_location, access_key, secret_key, region)
    return s3_file.get()['Body'].read().decode('utf-8')


def get_s3_object(
    bucket_name, file_location, access_key, secret_key, region
):
    session = Session(aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=region)
    s3 = session.resource('s3')
    return s3.Object(bucket_name, file_location)


def file_exists(
    bucket_name, file_location, access_key, secret_key, region
):
    try:
        # try and access metadata of object
        get_s3_object(bucket_name, file_location, access_key, secret_key, region).metadata
        return True
    except botocore.exceptions.ClientError as e:
        if e.response['ResponseMetadata']['HTTPStatusCode'] == 404:
            return False
        raise


def get_job_location(service_id, job_id):
    return (
        current_app.config['CSV_UPLOAD_BUCKET']['bucket'],
        FILE_LOCATION_STRUCTURE.format(service_id, job_id),
        current_app.config['CSV_UPLOAD_BUCKET']['access_key_id'],
        current_app.config['CSV_UPLOAD_BUCKET']['secret_access_key'],
        current_app.config['CSV_UPLOAD_BUCKET']['region'],
    )


def get_job_and_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()['Body'].read().decode('utf-8'), obj.get()['Metadata']


def get_job_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()['Body'].read().decode('utf-8')


def get_job_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()['Metadata']


def remove_job_from_s3(service_id, job_id):
    return remove_s3_object(*get_job_location(service_id, job_id))


def remove_s3_object(bucket_name, object_key, access_key, secret_key, region):
    obj = get_s3_object(bucket_name, object_key, access_key, secret_key, region)
    return obj.delete()
