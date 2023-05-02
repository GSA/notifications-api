# How messages are queued and sent

There are several ways for notifications to come into the API.

- Messages sent through the API enter through `app/notifications/post_notifications.py`
- One-off messages sent from the UI enter through `create_one_off_notification` in `app/service/rest.py`
- CSV uploads enter through `app/job/rest.py`

API messages and one-off UI messages come in one at a time, and take slightly-separate routes
that both end up at `persist_notification`, which writes to the database, and `provider_tasks.deliver_sms`,
which enqueues the sending.

For CSV uploads, the CSV is first stored in S3 and queued as a `Job`. When the job runs, it iterates
through the rows, running `process_job.save_sms` to send notifications through `persist_notification` and 
`provider_tasks.deliver_sms`.
