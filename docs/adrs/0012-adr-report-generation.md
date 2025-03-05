# Optimize processing of delivery receipts

Status: Accepted
Date: 12 February 2025

### Context

In the original UK code, there is a notifications table in the database that stores all the recipient phone numbers and emails.  Even though this data is purged after seven days, there could be hundreds of thousands or millions of rows of data with PII at any given time.  We were concerned about this for security reasons as any kind of database breach would leak a lot of PII.

### Decision

We decided to move PII out of the database.  It would continue to exist in the form of uploaded CSV files in S3 for seven days, but this would be substantially reducing the attack service.

However, in doing so, it complicated the generation of reports, which contained the recipients phone numbers.   There was some debate about whether the reports should contain the recipients' phone numbers at all, but there was considerable pushback from partners when we tried to remove them.

Being informed that Redis was not an option to store this PII either, we decided to try to creating a short term caching solution that would hold onto all the phone numbers and allow report generation as before.  This caching solution involved the use of a ThreadPoolExecutor to allow the download of multiple S3 files at the same time, as well as a multiprocessing.Manager that would allow us to create a dictionary that could be shared across all celery workers.


### Consequences

Initially this approach seemed relatively promising as most of the time partners were able to generate their reports.  However, these were early beta partners who typically sent low volumes of texts.  In retrospect, the fact that there were recurrent occasional failures should have been a red flag.  As the partner usage started to scale up, reports rapidly became unusable.

This whole problem could be solved in a day if we replaced the multiprocessing.Manager with Redis, but that would essentially take us back to where we were where we started, with PII persisting in two locations.

The direction we intend to go is to remove phone numbers from the reports.  However, that work is still in progress as we are trying to find how to make that solution palatable to partners.


### Author
@kenkehl

### Stakeholders
@ccostino
@stvnrlly
