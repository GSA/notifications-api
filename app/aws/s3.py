import csv
import datetime
import re
import time
from io import StringIO

import botocore
import eventlet
from boto3 import Session
from flask import current_app

from app.clients import AWS_CLIENT_CONFIG
from notifications_utils import aware_utcnow

FILE_LOCATION_STRUCTURE = "service-{}-notify/{}.csv"
NEW_FILE_LOCATION_STRUCTURE = "{}-service-notify/{}.csv"

# Temporarily extend cache to 7 days
ttl = 60 * 60 * 24 * 7


# Global variable
s3_client = None
s3_resource = None


def get_service_id_from_key(key):
    key = key.replace("service-", "")
    key = key.split("/")
    key = key[0].replace("-notify", "")
    return key


def set_job_cache(key, value):
    current_app.logger.debug(f"Setting {key} in the job_cache to {value}.")
    job_cache = current_app.config["job_cache"]
    job_cache[key] = (value, time.time() + 8 * 24 * 60 * 60)


def get_job_cache(key):
    job_cache = current_app.config["job_cache"]
    ret = job_cache.get(key)
    if ret is None:
        current_app.logger.warning(f"Could not find {key} in the job_cache.")
    else:
        current_app.logger.debug(f"Got {key} from job_cache with value {ret}.")
    return ret


def len_job_cache():
    job_cache = current_app.config["job_cache"]
    ret = len(job_cache)
    current_app.logger.debug(f"Length of job_cache is {ret}")
    return ret


def clean_cache():
    job_cache = current_app.config["job_cache"]
    current_time = time.time()
    keys_to_delete = []
    for key, (_, expiry_time) in job_cache.items():
        if expiry_time < current_time:
            keys_to_delete.append(key)

    current_app.logger.debug(
        f"Deleting the following keys from the job_cache: {keys_to_delete}"
    )
    for key in keys_to_delete:
        del job_cache[key]


def get_s3_client():
    global s3_client
    if s3_client is None:
        access_key = current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"]
        secret_key = current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"]
        region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]
        session = Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        s3_client = session.client("s3")
    return s3_client


def get_s3_resource():
    global s3_resource
    if s3_resource is None:
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


def _get_bucket_name():
    return current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]


def list_s3_objects():

    bucket_name = _get_bucket_name()
    s3_client = get_s3_client()
    # Our reports only support 7 days, but pull 8 days to avoid
    # any edge cases
    time_limit = aware_utcnow() - datetime.timedelta(days=8)
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        while True:
            for obj in response.get("Contents", []):
                if obj["LastModified"] >= time_limit:
                    yield obj["Key"]
            if "NextContinuationToken" in response:
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    ContinuationToken=response["NextContinuationToken"],
                )
            else:
                break
    except Exception as e:
        current_app.logger.exception(
            f"An error occurred while regenerating cache #notify-debug-admin-1200: {str(e)}",
        )


def get_bucket_name():
    return current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]


def cleanup_old_s3_objects():
    bucket_name = get_bucket_name()

    s3_client = get_s3_client()
    # Our reports only support 7 days, but can be scheduled 3 days in advance
    # Use 14 day for the v1.0 version of this behavior
    time_limit = aware_utcnow() - datetime.timedelta(days=14)
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name)
        while True:
            for obj in response.get("Contents", []):
                if obj["LastModified"] <= time_limit:

                    try:
                        remove_csv_object(obj["Key"])
                        current_app.logger.debug(
                            f"#delete-old-s3-objects Deleted: {obj['LastModified']} {obj['Key']}"
                        )
                    except botocore.exceptions.ClientError:
                        current_app.logger.exception(f"Couldn't delete {obj['Key']}")

            if "NextContinuationToken" in response:
                response = s3_client.list_objects_v2(
                    Bucket=bucket_name,
                    ContinuationToken=response["NextContinuationToken"],
                )
            else:
                break
    except Exception:
        current_app.logger.exception(
            "#delete-old-s3-objects An error occurred while cleaning up old s3 objects",
        )


def get_job_id_from_s3_object_key(key):
    object_arr = key.split("/")
    job_id = object_arr[1]  # get the job_id
    job_id = job_id.replace(".csv", "")  # we just want the job_id
    return job_id


def read_s3_file(bucket_name, object_key, s3res):
    """
    This method runs during the 'regenerate job cache' task.
    Note that in addition to retrieving the jobs and putting them
    into the cache, this method also does some pre-processing by
    putting a list of all phone numbers into the cache as well.

    This means that when the report needs to be regenerated, it
    can easily find the phone numbers in the cache through job_cache[<job_id>_phones]
    and the personalization through job_cache[<job_id>_personalisation], which
    in theory should make report generation a lot faster.

    We are moving processing from the front end where the user can see it
    in wait time, to this back end process.
    """
    try:
        job_id = get_job_id_from_s3_object_key(object_key)
        service_id = get_service_id_from_key(object_key)

        if get_job_cache(job_id) is None:
            job = (
                s3res.Object(bucket_name, object_key)
                .get()["Body"]
                .read()
                .decode("utf-8")
            )
            set_job_cache(job_id, job)
            set_job_cache(f"{job_id}_phones", extract_phones(job, service_id, job_id))
            set_job_cache(
                f"{job_id}_personalisation",
                extract_personalisation(job),
            )

    except LookupError:
        # perhaps our key is not formatted as we expected.  If so skip it.
        current_app.logger.exception("LookupError #notify-debug-admin-1200")


def get_s3_files():
    """
    We're using the ThreadPoolExecutor here to speed up the retrieval of S3
    csv files for scaling needs.
    """
    bucket_name = current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]
    object_keys = list_s3_objects()

    s3res = get_s3_resource()
    current_app.logger.info(
        f"job_cache length before regen: {len_job_cache()} #notify-debug-admin-1200"
    )
    count = 0
    try:
        for object_key in object_keys:
            read_s3_file(bucket_name, object_key, s3res)
            count = count + 1
            eventlet.sleep(0.2)
    except Exception:
        current_app.logger.exception(
            f"Trouble reading {object_key} which is # {count} during cache regeneration"
        )
    except OSError as e:
        current_app.logger.exception(
            f"Egress proxy issue reading {object_key} which is # {count}"
        )
        raise e

    current_app.logger.info(
        f"job_cache length after regen: {len_job_cache()} #notify-debug-admin-1200"
    )


def get_s3_file(bucket_name, file_location, access_key, secret_key, region):
    s3_file = get_s3_object(bucket_name, file_location, access_key, secret_key, region)
    return s3_file.get()["Body"].read().decode("utf-8")


def download_from_s3(
    bucket_name, s3_key, local_filename, access_key, secret_key, region
):

    s3 = get_s3_client()
    result = None
    try:
        result = s3.download_file(bucket_name, s3_key, local_filename)
        current_app.logger.info(f"File downloaded successfully to {local_filename}")
    except botocore.exceptions.NoCredentialsError as nce:
        current_app.logger.exception("Credentials not found")
        raise Exception(nce)
    except botocore.exceptions.PartialCredentialsError as pce:
        current_app.logger.exception("Incomplete credentials provided")
        raise Exception(pce)
    except Exception:
        current_app.logger.exception("An error occurred")
        text = f"EXCEPTION local_filename {local_filename}"
        raise Exception(text)
    return result


def get_s3_object(bucket_name, file_location, access_key, secret_key, region):

    s3 = get_s3_resource()
    try:
        return s3.Object(bucket_name, file_location)
    except botocore.exceptions.ClientError:
        current_app.logger.exception(
            f"Can't retrieve S3 Object from {file_location}",
        )


def purge_bucket(bucket_name, access_key, secret_key, region):
    s3 = get_s3_resource()
    bucket = s3.Bucket(bucket_name)
    bucket.objects.all().delete()


def file_exists(file_location):
    bucket_name = current_app.config["CSV_UPLOAD_BUCKET"]["bucket"]
    access_key = current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"]
    secret_key = current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"]
    region = current_app.config["CSV_UPLOAD_BUCKET"]["region"]

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
    current_app.logger.debug(
        f"#notify-debug-s3-partitioning NEW JOB_LOCATION: {NEW_FILE_LOCATION_STRUCTURE.format(service_id, job_id)}"
    )
    return (
        current_app.config["CSV_UPLOAD_BUCKET"]["bucket"],
        NEW_FILE_LOCATION_STRUCTURE.format(service_id, job_id),
        current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"],
        current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"],
        current_app.config["CSV_UPLOAD_BUCKET"]["region"],
    )


def get_old_job_location(service_id, job_id):
    """
    This is deprecated. We are transitioning to NEW_FILE_LOCATION_STRUCTURE,
    but it will take a few days where we have to support both formats.
    Remove this when everything works with the NEW_FILE_LOCATION_STRUCTURE.
    """
    current_app.logger.debug(
        f"#notify-debug-s3-partitioning OLD JOB LOCATION: {FILE_LOCATION_STRUCTURE.format(service_id, job_id)}"
    )
    return (
        current_app.config["CSV_UPLOAD_BUCKET"]["bucket"],
        FILE_LOCATION_STRUCTURE.format(service_id, job_id),
        current_app.config["CSV_UPLOAD_BUCKET"]["access_key_id"],
        current_app.config["CSV_UPLOAD_BUCKET"]["secret_access_key"],
        current_app.config["CSV_UPLOAD_BUCKET"]["region"],
    )


def get_job_and_metadata_from_s3(service_id, job_id):
    try:
        obj = get_s3_object(*get_job_location(service_id, job_id))
    except botocore.exceptions.ClientError:
        obj = get_s3_object(*get_old_job_location(service_id, job_id))

    return obj.get()["Body"].read().decode("utf-8"), obj.get()["Metadata"]


def get_job_from_s3(service_id, job_id):
    """
    If and only if we hit a throttling exception of some kind, we want to try
    exponential backoff.  However, if we are getting NoSuchKey or something
    that indicates things are permanently broken, we want to give up right away
    to save time.
    """
    # We have to make sure the retries don't take up to much time, because
    # we might be retrieving dozens of jobs.  So max time is:
    # 0.2 + 0.4 + 0.8 + 1.6 = 3.0 seconds
    retries = 0
    max_retries = 4
    backoff_factor = 0.2

    if not file_exists(
        FILE_LOCATION_STRUCTURE.format(service_id, job_id)
    ) and not file_exists(NEW_FILE_LOCATION_STRUCTURE.format(service_id, job_id)):
        current_app.logger.error(
            f"This file with service_id {service_id} and job_id {job_id} does not exist"
        )
        return None

    while retries < max_retries:

        try:
            # TODO
            # for transition on optimizing the s3 partition, we have
            # to check for the file location using the new way and the
            # old way.  After this has been on production for a few weeks
            # we should remove the check for the old way.
            try:
                obj = get_s3_object(*get_job_location(service_id, job_id))
                return obj.get()["Body"].read().decode("utf-8")
            except botocore.exceptions.ClientError:
                obj = get_s3_object(*get_old_job_location(service_id, job_id))
                return obj.get()["Body"].read().decode("utf-8")
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] in [
                "Throttling",
                "RequestTimeout",
                "SlowDown",
            ]:
                current_app.logger.exception(
                    f"Retrying job fetch service_id {service_id} job_id {job_id} retry_count={retries}",
                )
                retries += 1
                sleep_time = backoff_factor * (2**retries)  # Exponential backoff
                eventlet.sleep(sleep_time)
                continue
            else:
                # Typically this is "NoSuchKey"
                current_app.logger.exception(
                    f"Failed to get job with service_id {service_id} job_id {job_id}",
                )
                return None

        except Exception:
            current_app.logger.exception(
                f"Failed to get job with service_id {service_id} job_id {job_id}retry_count={retries}",
            )
            return None

    current_app.logger.error(
        f"Never retrieved job with service_id {service_id} job_id {job_id}",
    )
    return None


def extract_phones(job, service_id, job_id):
    job_csv_data = StringIO(job)
    csv_reader = csv.reader(job_csv_data)
    first_row = next(csv_reader)

    phone_index = 0
    for i, item in enumerate(first_row):
        if item.lower().lstrip("\ufeff") == "phone number":
            phone_index = i
            break

    phones = {}
    job_row = 0
    for row in csv_reader:

        if phone_index >= len(row):
            phones[job_row] = "Unavailable"
            current_app.logger.error(
                f"Corrupt csv file, missing columns or\
                possibly a byte order mark in the file, \
                row: {row} service_id {service_id} job_id {job_id}",
            )
            # If the file is corrupt, stop trying to process it.
            return phones
        else:
            my_phone = row[phone_index]
            my_phone = re.sub(r"[\+\s\(\)\-\.]*", "", my_phone)
            phones[job_row] = my_phone
        job_row = job_row + 1
    return phones


def extract_personalisation(job):
    if isinstance(job, dict):
        job = job[0]
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
    job = get_job_cache(job_id)
    if job is None:
        current_app.logger.debug(f"job {job_id} was not in the cache")
        job = get_job_from_s3(service_id, job_id)
        # Even if it is None, put it here to avoid KeyErrors
        set_job_cache(job_id, job)
    else:
        # skip expiration date from cache, we don't need it here
        job = job[0]

    if job is None:
        current_app.logger.error(
            f"Couldnt find phone for job with service_id {service_id} job_id {job_id} because job is missing"
        )
        return "Unavailable"

    phones = extract_phones(job, service_id, job_id)
    set_job_cache(f"{job_id}_phones", phones)

    # If we can find the quick dictionary, use it
    phone_to_return = phones[job_row_number]
    if phone_to_return:
        return phone_to_return
    else:
        current_app.logger.warning(
            f"Was unable to retrieve phone number from lookup dictionary for job {job_id}"
        )
        return "Unavailable"


def get_personalisation_from_s3(service_id, job_id, job_row_number):
    # We don't want to constantly pull down a job from s3 every time we need the personalisation.
    # At the same time we don't want to store it in redis or the db
    # So this is a little recycling mechanism to reduce the number of downloads.
    job = get_job_cache(job_id)
    if job is None:
        current_app.logger.debug(f"job {job_id} was not in the cache")
        job = get_job_from_s3(service_id, job_id)
        # Even if it is None, put it here to avoid KeyErrors
        set_job_cache(job_id, job)
    else:
        # skip expiration date from cache, we don't need it here
        job = job[0]
    # If the job is None after our attempt to retrieve it from s3, it
    # probably means the job is old and has been deleted from s3, in
    # which case there is nothing we can do.  It's unlikely to run into
    # this, but it could theoretically happen, especially if we ever
    # change the task schedules
    if job is None:
        current_app.logger.warning(
            f"Couldnt find personalisation for job_id {job_id} row number {job_row_number} because job is missing"
        )
        return {}

    set_job_cache(f"{job_id}_personalisation", extract_personalisation(job))

    return get_job_cache(f"{job_id}_personalisation")[0].get(job_row_number)


def get_job_metadata_from_s3(service_id, job_id):
    current_app.logger.debug(
        f"#notify-debug-s3-partitioning CALLING GET_JOB_METADATA with {service_id}, {job_id}"
    )
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
