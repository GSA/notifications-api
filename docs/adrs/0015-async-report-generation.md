# Improve API stability when processing job data and generating reports

Status: Accepted
Date: 11 August 2025

### Context

We're currently facing a scaling issue with our app that is leading to unstable conditions due to increased load in the system.  At the moment, we have a job cache that is intended to help with the performance of generating reports based on all of the message sending jobs (both one-offs and batch sends).  The idea was to cache the information being sent by these jobs so it could be quickly pulled when viewing the job status and/or 1, 3, 5, and 7 day reports.

We also have the added constraint of not storing any PII in the system, meaning we do not have any PII in any DB or Redis instances, hence the reason for opting for some kind of in-memory cache within the app process for a short duration period (maximum of 7 days).

This cache was ultimately implemented as a [`multiprocessing.managers.SyncManager.dict`](https://docs.python.org/3/library/multiprocessing.html#multiprocessing.managers.SyncManager.dict) - a proxy to a dictionary object that could be shared between processes.  However, this has proven problematic within our existing application architecture and environment and is prone to failure and instability after a short period of time and use.

We've tried thinking through other ways we might be able to make this work, but they all point to the need of a single app instance to serve as the entry point to the shared object, which will not work within the Cloud Foundry-based environment our system is hosted in.

### Decision

At this point, we will move away from the shared dictionary cache and convert it to a regular Python dictionary that is regenerated at app startup and refreshed every 30 minutes; this will continue to be used as a cache for phone numbers and personalization.  Furthermore, the reports themselves will be switched to being regenerated each night via asynchronous tasks.  The generated reports are stored in an S3 bucket for a maximum of 7 days.

Additionally, we'll need a bit of UI work to update the links to the reports and some additional language to indicate that they are regenerated on a 24 hour basis and won't contain any of the current day's send information until the following day.

We did try shifting the creation and management of the shared dictionary for the job cache to the main application instances and this initially improved things, but it fell over fast once a few reports were generated.  A host of connection refused errors started cropping up, and any action that touched the job cache, including sending messages, resulted in an error being displayed to users (despite the action still succeeded in the case of sending messages).

Further investigation into using anything with [`multiprocessing`](https://docs.python.org/3/library/multiprocessing.html) was showing that many other moving parts need to be introduced to properly use it, which would greatly increase the complexity of our application architecture and introduce more brittle moving parts.

### Consequences

By making this switch to using Celery itself for our longer-running actions performed by users, we trade off some data freshness for improved performance and stability.  Asynchronous tasks aren't necessarily simple either, but it's a known paradigm and by simply leveraging them and not trying to do additional processing for performance gains, we can go with a tried and true approach.

We will need to do some additional UI work to support the switch to using the nightly-generated reports, but this is minimal in nature compared to trying to fully support a shared cache solely within a running app process(es).

Again, we will gain a significant amount of application stability and resiliency without having to increase our resource usage by taking this approach.  We will also buy ourselves time and breathing room to take another look at the performance afterward and see what we can do to improve the report generation in the future with other approaches to how we process the data under the hood.

### Author

@ccostino

### Stakeholders

@ccostino, @CathyBeil

### Next Steps

Already implemented
