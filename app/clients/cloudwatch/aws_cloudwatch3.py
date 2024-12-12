from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
from datetime import datetime, timedelta, timezone
import threading
from time import sleep, strptime, time
from typing import Protocol
from zoneinfo import ZoneInfo

import boto3
from botocore.config import Config
from flask import current_app

OUTPUT_CSV = "output.csv" # The final product
ORIGINAL_CENSUS_CSV = "census_8cbcc66e_1203.csv"
ALL_RESULTS = "all_results.csv"   # All results we have gotten from cloudwatch for a time range



# Secrets
AWS_ACCESS_KEY_ID="XXXXX" # production
# Commented out due to secrets detector!
# AWS_SEC   RET_ACCESS_KEY="XXXXX", #production
LOG_GROUP_NAME_DELIVERED = f"sns/us-gov-west-1/XXXXX/DirectPublishToPhoneNumber"
LOG_GROUP_NAME_FAILED = f"sns/us-gov-west-1/XXXXX/DirectPublishToPhoneNumber/Failure"

class Client(Protocol):
    """
    Base client for sending notifications.
    """

    def init_app(self, current_app, *args, **kwargs):
        raise NotImplementedError("TODO: Need to implement.")


AWS_CLIENT_CONFIG = Config(
    # This config is required to enable S3 to connect to FIPS-enabled
    # endpoints.  See https://aws.amazon.com/compliance/fips/ for more
    # information.
    s3={
        "addressing_style": "virtual",
    },
    use_fips_endpoint=True,
    # This is the default but just for doc sake
    max_pool_connections=10,
)


class AwsCloudwatchClient3(Client):
    """
    This client is responsible for retrieving sms delivery receipts from cloudwatch.
    """

    def init_app(self, current_app, *args, **kwargs):
        self._client = boto3.client(
            "logs",
            region_name="us-gov-west-1",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            config=AWS_CLIENT_CONFIG,
        )

        super(Client, self).__init__(*args, **kwargs)
        self.current_app = current_app
        self._valid_sender_regex = re.compile(r"^\+?\d{5,14}$")

    # Right now this is the same method we use in production
    # Superficially it looks right but maybe there are edge cases?
    def _get_log(self, my_filter, log_group_name, start, end):
        start = start.timestamp() * 1000
        end = end.timestamp() * 1000
        start = int(start)
        end = int(end)
        # print(f"filter {my_filter} log_group_name {log_group_name} start {start} end {end}")
        next_token = None
        all_log_events = []

        while True:
            if next_token:
                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    nextToken=next_token,
                    startTime=start,
                    endTime=end,
                )
                #print(f"!!!START {start} END {end} next_token {next_token} len(response) {len(response)}")
            else:

                response = self._client.filter_log_events(
                    logGroupName=log_group_name,
                    filterPattern=my_filter,
                    startTime=start,
                    endTime=end,
                )

            log_events = response.get("events", [])
            all_log_events.extend(log_events)
            if len(log_events) > 0:
                # We found it

                break
            next_token = response.get("nextToken")
            if not next_token:
                break
        return all_log_events


# Massage the JSON we get from AWS Cloudwatch into our report format
def write_to_report(result, report_name):
    if isinstance(result, str):
        result = json.loads(result)

    if result.get("delivery") is None:
        result = result["message"]
        if isinstance(result, str):
            result = json.loads(result)

    phone = result["delivery"]["destination"]
    carrier = ""
    if result["delivery"].get("phoneCarrier"):
        carrier = result["delivery"]["phoneCarrier"]
    timestamp = ""
    if result["notification"].get("timestamp"):
        timestamp = result["notification"]["timestamp"]
        utc_time = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        est_time = utc_time.astimezone(ZoneInfo("America/New_York"))
        formatted_time = est_time.strftime("%m-%d-%Y at %I:%M %p")
        timestamp = formatted_time
    carrier_response = result["delivery"]["providerResponse"]
    status = result["status"]
    if status == "SUCCESS":
        status = "Delivered"
    elif status == "FAILURE":
        status = "Failed"
    else:
        status = "Pending"
    with open(report_name, "a") as f:
        f.write(f"{phone},{status},{timestamp},{carrier},{carrier_response}\n")

# Get all delivery receipts from CloudWatch for a given time chunk a thread-safe way
def fetch_logs_chunk(client, log_group, start_time, end_time, filter_pattern, semaphore):
    temp_client = boto3.client(
            "logs",
            region_name="us-gov-west-1",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            config=AWS_CLIENT_CONFIG,
        )
    print(f"working on chunk ending {end_time}")
    events = []
    next_token = None
    delay = 0.2
    with semaphore:
        while True:
            params = {
                'logGroupName': log_group,
                'startTime': int(start_time.timestamp() * 1000),
                'endTime': int(end_time.timestamp() * 1000),
                'filterPattern': filter_pattern,
            }
            if next_token:
                params['nextToken'] = next_token
            try:
                print(f"calling")
                response = temp_client.filter_log_events(**params)
                print(f"got response")
                events.extend(response.get('events', []))
                next_token = response.get('nextToken')
                delay = max(0.2, delay / 2)
            except temp_client.exceptions.ThrottlingException:
                delay *= 2
                print(f"Throttling detected.  Increasing delay to {delay:.2f} seconds")
                sleep(delay)
            if not next_token:
                break
        print(f"finished with chunk ending {end_time}")
        return events

# Fetch all logs parallelly in time chunks and assemble one complete list of delivery receipts
# for a large time range
def parallel_fetch_logs(client, log_group, start_time, end_time, filter_pattern, chunk_size=10):
    time_chunks = []
    current_time = start_time
    while current_time < end_time:
        chunk_end = min(current_time + timedelta(minutes=chunk_size), end_time)
        time_chunks.append((current_time, chunk_end))
        current_time = chunk_end

    semaphore = threading.Semaphore(1)
    all_events = []
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = [
            executor.submit(fetch_logs_chunk, client, log_group, chunk[0], chunk[1], filter_pattern, semaphore)
            for chunk in time_chunks
        ]
        for future in futures:
            all_events.extend(future.result())
    return all_events

def generate_final_report():
    # Load the results into an array
    # Then load all the phone numbers for a given Census csv file into an array (phones)
    # Walk through the list of phone numbers for a given Census send, and see if you can find
    # the result in the "all results" array.  If so, copy it to the output file
    all_results = []
    with open(ALL_RESULTS, "r") as f:
        lines = f.readlines()
        for line in lines:
            all_results.append(line.strip())

    phones = []
    with open(ORIGINAL_CENSUS_CSV, "r") as f:
        lines = f.readlines()
        lines.pop(0)
        for line in lines:
            phones.append(line.strip())

    print(f"LENGTH PHONES {len(phones)}")

    with open(OUTPUT_CSV, "a") as f:
        f.write("Phone Number,Status,Delivered At,Carrier,Carrier Response\n")

        count = 1
        for result in all_results:
            check = result.split(",")
            phone_to_check = check[0]
            phone_to_check = phone_to_check.replace("+","")
            if phone_to_check in phones:
                f.write(f"{result}\n")
                print(f"writing result #{count}")
                count = count + 1
            else:
                 print(f"phone {phone_to_check} did not match a phone in the list")

def main():

    client = AwsCloudwatchClient3()
    client.init_app(None)
    delivered = []
    failed = []
    pending = []

    # I did this to try to debug my credentials with an easier use case, it is not part of the app
    # try:
    #     sts = boto3.client(
    #         "sts",
    #         region_name="us-gov-west-1",
    #         aws_access_key_id=AWS_ACCESS_KEY_ID,
    #         aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    #         config=AWS_CLIENT_CONFIG,
    #     )
    #     response = sts.get_caller_identity()
    #     print(response)
    # except Exception as e:
    #     print(f"Error: {e}")
    # return

    # Build up a giant file of receipts with a given time range
    # NOTE: I made a couple changes after my credentials changes so there should be minor cleanup but not bad!
    # NOTE: Right now the range is set for just 2 hours to test that this works.  If it works, it should
    # be set to the full range.  Easiest is 12,3,6,0 to 12,9,0,0  Which would cover all the reports they ran on 12/3, 12/4, and I think 12/6
    start_time = datetime(2024, 12, 3, 6, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    end_time = datetime(2024, 12, 3, 8, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
    filter_pattern = '{ $.delivery.phoneCarrier = "*" }'
    event_set = {}
    for chunk_size in range(7, 10):
        all_delivered_events = parallel_fetch_logs(client, LOG_GROUP_NAME_DELIVERED, start_time, end_time, filter_pattern, chunk_size)
        all_failed_events = parallel_fetch_logs(client, LOG_GROUP_NAME_FAILED, start_time, end_time, filter_pattern, chunk_size)
        event_set.update(all_delivered_events)
        event_set.update(all_failed_events)
        print(f"After chunk_size {chunk_size} the event_size is size {len(event_set)}")
    for event in event_set:
        write_to_report(event, ALL_RESULTS)

    # To generate the final report you have to have downloaded the relevant Census csv from the secret location
    # generate_final_report()




if __name__ == "__main__":
    main()
