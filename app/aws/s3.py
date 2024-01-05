import botocore
from boto3 import Session
from expiringdict import ExpiringDict
from flask import current_app

from app.clients import AWS_CLIENT_CONFIG

FILE_LOCATION_STRUCTURE = "service-{}-notify/{}.csv"


JOBS = ExpiringDict(max_len=100, max_age_seconds=3600)


def get_s3_file(bucket_name, file_location, access_key, secret_key, region):
    s3_file = get_s3_object(bucket_name, file_location, access_key, secret_key, region)
    return s3_file.get()["Body"].read().decode("utf-8")


def get_s3_object(bucket_name, file_location, access_key, secret_key, region):
    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    s3 = session.resource("s3", config=AWS_CLIENT_CONFIG)
    return s3.Object(bucket_name, file_location)


def purge_bucket(bucket_name, access_key, secret_key, region):
    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    s3 = session.resource("s3", config=AWS_CLIENT_CONFIG)
    bucket = s3.Bucket(bucket_name)
    bucket.objects.all().delete()


def file_exists(bucket_name, file_location, access_key, secret_key, region):
    try:
        # try and access metadata of object
        get_s3_object(
            bucket_name, file_location, access_key, secret_key, region
        ).metadata
        return True
    except botocore.exceptions.ClientError as e:
        if e.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
            return False
        raise


def get_job_location(service_id, job_id):
    return (
        current_app.config["CSV_UPLOAD_BUCKET"]["bucket"],
        FILE_LOCATION_STRUCTURE.format(service_id, job_id),
        current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"],
        current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"],
        current_app.config["CSV_UPLOAD_BUCKET"]["region"],
    )


def get_job_and_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()["Body"].read().decode("utf-8"), obj.get()["Metadata"]


def get_job_from_s3(service_id, job_id):
    print(f"ENTERE get_job_from_s3 with {service_id} {job_id}")
    obj = get_s3_object(*get_job_location(service_id, job_id))
    print(f"obj is {obj}")
    return obj.get()["Body"].read().decode("utf-8")


def get_phone_number_from_s3(service_id, job_id, job_row_number):
    # We don't want to constantly pull down a job from s3 every time we need a phone number.
    # At the same time we don't want to store it in redis or the db
    # So this is a little recycling mechanism to reduce the number of downloads.
    print(
        f"ENTER GET_PHONE_NUMBER_FROM_S3 WITH JOB_ID {job_id} SERVICE_ID {service_id} JOB_ROW_NUMBER {job_row_number}"
    )
    job = JOBS.get(job_id)
    print(f"JOB FROM EXPIRINGDICT {job} JOB ID {job_id}")
    if job is None:
        print("JOB IS NONE")
        job = get_job_from_s3(service_id, job_id)
        print(f"FRESH JOB {job}")
        JOBS[job_id] = job
        print("ADDED {job} to EXPRING DICT")
    else:
        print("JOB IS NOT NONE")
    job = job.split("\r\n")
    print(f"JOB AFTER SPLIT {job}")
    first_row = job[0]
    job.pop(0)
    first_row = first_row.split(",")
    phone_index = 0
    for item in first_row:
        if item == "phone number":
            break
        phone_index = phone_index + 1
    correct_row = job[job_row_number]
    correct_row = correct_row.split(",")

    my_phone = correct_row[phone_index]
    my_phone = my_phone.replace("(", "")
    my_phone = my_phone.replace(")", "")
    my_phone = my_phone.replace("-", "")
    my_phone = my_phone.replace(" ", "")
    my_phone = my_phone.replace("+", "")
    return my_phone


def get_job_metadata_from_s3(service_id, job_id):
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()["Metadata"]


def remove_job_from_s3(service_id, job_id):
    return remove_s3_object(*get_job_location(service_id, job_id))


def remove_s3_object(bucket_name, object_key, access_key, secret_key, region):
    obj = get_s3_object(bucket_name, object_key, access_key, secret_key, region)
    return obj.delete()


def remove_csv_object(object_key):
    obj = get_s3_object(
        current_app.config["CSV_UPLOAD_BUCKET"]["bucket"],
        object_key,
        current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"],
        current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"],
        current_app.config["CSV_UPLOAD_BUCKET"]["region"],
    )
    return obj.delete()
