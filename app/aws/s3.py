import re

import botocore
from boto3 import Session
from expiringdict import ExpiringDict
from flask import current_app

from app import redis_store
from app.clients import AWS_CLIENT_CONFIG

FILE_LOCATION_STRUCTURE = "service-{}-notify/{}.csv"


JOBS = ExpiringDict(max_len=100, max_age_seconds=3600 * 4)

JOBS_CACHE_HITS = "JOBS_CACHE_HITS"
JOBS_CACHE_MISSES = "JOBS_CACHE_MISSES"


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
    obj = get_s3_object(*get_job_location(service_id, job_id))
    return obj.get()["Body"].read().decode("utf-8")


def incr_jobs_cache_misses():
    if not redis_store.get(JOBS_CACHE_MISSES):
        redis_store.set(JOBS_CACHE_MISSES, 1)
    else:
        redis_store.incr(JOBS_CACHE_MISSES)
    hits = redis_store.get(JOBS_CACHE_HITS).decode("utf-8")
    misses = redis_store.get(JOBS_CACHE_MISSES).decode("utf-8")
    current_app.logger.info(f"JOBS CACHE MISS hits {hits} misses {misses}")


def incr_jobs_cache_hits():
    if not redis_store.get(JOBS_CACHE_HITS):
        redis_store.set(JOBS_CACHE_HITS, 1)
    else:
        redis_store.incr(JOBS_CACHE_HITS)
    hits = redis_store.get(JOBS_CACHE_HITS).decode("utf-8")
    misses = redis_store.get(JOBS_CACHE_MISSES).decode("utf-8")
    current_app.logger.info(f"JOBS CACHE MISS hits {hits} misses {misses}")


def get_phone_number_from_s3(service_id, job_id, job_row_number):
    # We don't want to constantly pull down a job from s3 every time we need a phone number.
    # At the same time we don't want to store it in redis or the db
    # So this is a little recycling mechanism to reduce the number of downloads.
    job = JOBS.get(job_id)
    if job is None:
        job = get_job_from_s3(service_id, job_id)
        JOBS[job_id] = job
        incr_jobs_cache_misses()
    else:
        incr_jobs_cache_hits()

    job = job.split("\r\n")
    first_row = job[0]
    job.pop(0)
    first_row = first_row.split(",")
    phone_index = 0
    for item in first_row:
        if item.lower() == "phone number":
            break
        phone_index = phone_index + 1

    correct_row = job[job_row_number]
    correct_row = correct_row.split(",")

    # This could happen if an old job cannot be retrieved from s3
    if len(correct_row) <= phone_index:
        return "Unknown Phone"
    my_phone = correct_row[phone_index]
    my_phone = re.sub(r"[\+\s\(\)\-\.]*", "", my_phone)
    return my_phone


def get_personalisation_from_s3(service_id, job_id, job_row_number):
    job = JOBS.get(job_id)
    if job is None:
        job = get_job_from_s3(service_id, job_id)
        JOBS[job_id] = job
        incr_jobs_cache_misses()
    else:
        incr_jobs_cache_hits()

    job = job.split("\r\n")
    first_row = job[0]
    job.pop(0)
    first_row = first_row.split(",")
    correct_row = job[job_row_number]
    correct_row = correct_row.split(",")
    personalisation_dict = {}
    index = 0
    for header in first_row:
        personalisation_dict[header] = correct_row[index]
        index = index + 1
    print(f"get personalisation returns {personalisation_dict}")
    return personalisation_dict


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
