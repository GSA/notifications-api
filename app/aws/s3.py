import re
import time

import botocore
from boto3 import Session
from expiringdict import ExpiringDict
from flask import current_app

from app import redis_store
from app.clients import AWS_CLIENT_CONFIG

FILE_LOCATION_STRUCTURE = "service-{}-notify/{}.csv"

# Temporarily extend cache to 7 days
ttl = 60 * 60 * 24 * 7
JOBS = ExpiringDict(max_len=20000, max_age_seconds=ttl)


JOBS_CACHE_HITS = "JOBS_CACHE_HITS"
JOBS_CACHE_MISSES = "JOBS_CACHE_MISSES"


def list_s3_objects():
    bucket_name = current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]
    access_key = current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"]
    secret_key = current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"]
    region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]
    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    s3 = session.client("s3")

    try:
        response = s3.list_objects_v2(Bucket=bucket_name)
        while True:
            for obj in response.get("Contents", []):
                yield obj["Key"]
            if "NextContinuationToken" in response:
                response = s3.list_objects_v2(
                    Bucket=bucket_name,
                    ContinuationToken=response["NextContinuationToken"],
                )
            else:
                break
    except Exception as e:
        current_app.logger.error(
            f"An error occurred while regenerating cache #notify-admin-1200 {e}"
        )


def get_s3_files():
    current_app.logger.info("Regenerate job cache #notify-admin-1200")
    bucket_name = current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]
    access_key = current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"]
    secret_key = current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"]
    region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]
    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    objects = list_s3_objects()

    s3res = session.resource("s3", config=AWS_CLIENT_CONFIG)
    current_app.logger.info(
        f"JOBS cache length before regen: {len(JOBS)} #notify-admin-1200"
    )
    for object in objects:
        # We put our csv files in the format "service-{service_id}-notify/{job_id}"
        try:
            object_arr = object.split("/")
            job_id = object_arr[1]  # get the job_id
            job_id = job_id.replace(".csv", "")  # we just want the job_id
            if JOBS.get(job_id) is None:
                object = (
                    s3res.Object(bucket_name, object)
                    .get()["Body"]
                    .read()
                    .decode("utf-8")
                )
                if "phone number" in object.lower():
                    JOBS[job_id] = object
        except LookupError as le:
            # perhaps our key is not formatted as we expected.  If so skip it.
            current_app.logger.error(f"LookupError {le} #notify-admin-1200")

    current_app.logger.info(
        f"JOBS cache length after regen: {len(JOBS)} #notify-admin-1200"
    )


def get_s3_file(bucket_name, file_location, access_key, secret_key, region):
    s3_file = get_s3_object(bucket_name, file_location, access_key, secret_key, region)
    return s3_file.get()["Body"].read().decode("utf-8")


def download_from_s3(
    bucket_name, s3_key, local_filename, access_key, secret_key, region
):
    session = Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
    s3 = session.client("s3", config=AWS_CLIENT_CONFIG)
    result = None
    try:
        result = s3.download_file(bucket_name, s3_key, local_filename)
        current_app.logger.info(f"File downloaded successfully to {local_filename}")
    except botocore.exceptions.NoCredentialsError as nce:
        current_app.logger.error("Credentials not found")
        raise Exception(nce)
    except botocore.exceptions.PartialCredentialsError as pce:
        current_app.logger.error("Incomplete credentials provided")
        raise Exception(pce)
    except Exception as e:
        current_app.logger.error(f"An error occurred {e}")
        text = f"EXCEPTION {e} local_filename {local_filename}"
        raise Exception(text)
    return result


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
    retries = 0
    max_retries = 3
    backoff_factor = 1
    while retries < max_retries:

        try:
            obj = get_s3_object(*get_job_location(service_id, job_id))
            return obj.get()["Body"].read().decode("utf-8")
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] in [
                "Throttling",
                "RequestTimeout",
                "SlowDown",
            ]:
                retries += 1
                sleep_time = backoff_factor * (2**retries)  # Exponential backoff
                time.sleep(sleep_time)
                continue
            else:
                current_app.logger.error("Failed to get job from bucket", exc_info=True)
                return None
        except Exception:
            current_app.logger.error("Failed to get job from bucket", exc_info=True)
            return None

    raise Exception("Failed to get object after 3 attempts")


def incr_jobs_cache_misses():
    if not redis_store.get(JOBS_CACHE_MISSES):
        redis_store.set(JOBS_CACHE_MISSES, 1)
    else:
        redis_store.incr(JOBS_CACHE_MISSES)


def incr_jobs_cache_hits():
    if not redis_store.get(JOBS_CACHE_HITS):
        redis_store.set(JOBS_CACHE_HITS, 1)
    else:
        redis_store.incr(JOBS_CACHE_HITS)


def extract_phones(job):
    job = job.split("\r\n")
    first_row = job[0]
    job.pop(0)
    first_row = first_row.split(",")
    phone_index = 0
    for item in first_row:
        # Note: may contain a BOM and look like \ufeffphone number
        if "phone number" in item.lower():
            break
        phone_index = phone_index + 1

    phones = {}
    job_row = 0
    for row in job:
        row = row.split(",")

        if phone_index >= len(row):
            phones[job_row] = "Unavailable"
            current_app.logger.error(
                "Corrupt csv file, missing columns or possibly a byte order mark in the file"
            )

        else:
            my_phone = row[phone_index]
            my_phone = re.sub(r"[\+\s\(\)\-\.]*", "", my_phone)
            phones[job_row] = my_phone
        job_row = job_row + 1
    return phones


def extract_personalisation(job):
    job = job.split("\r\n")
    first_row = job[0]
    job.pop(0)
    first_row = first_row.split(",")
    personalisation = {}
    job_row = 0
    for row in job:
        row = row.split(",")
        temp = dict(zip(first_row, row))
        personalisation[job_row] = temp
        job_row = job_row + 1
    return personalisation


def get_phone_number_from_s3(service_id, job_id, job_row_number):
    # We don't want to constantly pull down a job from s3 every time we need a phone number.
    # At the same time we don't want to store it in redis or the db
    # So this is a little recycling mechanism to reduce the number of downloads.
    job = JOBS.get(job_id)
    if job is None:
        current_app.logger.info(f"job {job_id} was not in the cache")
        job = get_job_from_s3(service_id, job_id)
        JOBS[job_id] = job
        incr_jobs_cache_misses()
    else:
        incr_jobs_cache_hits()

    # If the job is None after our attempt to retrieve it from s3, it
    # probably means the job is old and has been deleted from s3, in
    # which case there is nothing we can do.  It's unlikely to run into
    # this, but it could theoretically happen, especially if we ever
    # change the task schedules
    if job is None:
        current_app.logger.warning(
            f"Couldnt find phone for job_id {job_id} row number {job_row_number} because job is missing"
        )
        return "Unavailable"

    # If we look in the JOBS cache for the quick lookup dictionary of phones for a given job
    # and that dictionary is not there, create it
    if JOBS.get(f"{job_id}_phones") is None:
        JOBS[f"{job_id}_phones"] = extract_phones(job)

    # If we can find the quick dictionary, use it
    if JOBS.get(f"{job_id}_phones") is not None:
        phone_to_return = JOBS.get(f"{job_id}_phones").get(job_row_number)
        if phone_to_return:
            return phone_to_return
        else:
            current_app.logger.warning(
                f"Was unable to retrieve phone number from lookup dictionary for job {job_id}"
            )
            return "Unavailable"
    else:
        current_app.logger.error(
            f"Was unable to construct lookup dictionary for job {job_id}"
        )
        return "Unavailable"


def get_personalisation_from_s3(service_id, job_id, job_row_number):
    # We don't want to constantly pull down a job from s3 every time we need the personalisation.
    # At the same time we don't want to store it in redis or the db
    # So this is a little recycling mechanism to reduce the number of downloads.
    job = JOBS.get(job_id)
    if job is None:
        job = get_job_from_s3(service_id, job_id)
        JOBS[job_id] = job
        incr_jobs_cache_misses()
    else:
        incr_jobs_cache_hits()

    # If the job is None after our attempt to retrieve it from s3, it
    # probably means the job is old and has been deleted from s3, in
    # which case there is nothing we can do.  It's unlikely to run into
    # this, but it could theoretically happen, especially if we ever
    # change the task schedules
    if job is None:
        current_app.logger.warning(
            "Couldnt find personalisation for job_id {job_id} row number {job_row_number} because job is missing"
        )
        return {}

    # If we look in the JOBS cache for the quick lookup dictionary of personalisations for a given job
    # and that dictionary is not there, create it
    if JOBS.get(f"{job_id}_personalisation") is None:
        JOBS[f"{job_id}_personalisation"] = extract_personalisation(job)

    # If we can find the quick dictionary, use it
    if JOBS.get(f"{job_id}_personalisation") is not None:
        personalisation_to_return = JOBS.get(f"{job_id}_personalisation").get(
            job_row_number
        )
        if personalisation_to_return:
            return personalisation_to_return
        else:
            current_app.logger.warning(
                f"Was unable to retrieve personalisation from lookup dictionary for job {job_id}"
            )
            return {}
    else:
        current_app.logger.error(
            f"Was unable to construct lookup dictionary for job {job_id}"
        )
        return {}


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
