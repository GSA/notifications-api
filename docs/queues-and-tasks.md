# Queues and tasks

The API puts tasks into Celery queues for dispatch.

There are a bunch of queues:
- priority tasks
- database tasks
- send sms tasks
- send email tasks
- research mode tasks
- reporting tasks
- job tasks
- retry tasks
- notify internal tasks
- service callbacks
- service callbacks retry
- letter tasks
- sms callbacks
- antivirus tasks
- save api email tasks
- save api sms tasks

And these tasks:
- check for missing rows in completed jobs
- check for services with high failure rates or sending to tv numbers
- check if letters still in created
- check if letters still pending virus check
- check job status
- create fake letter response file
- create nightly billing
- create nightly billing for day
- create nightly notification status
- create nightly notification status for service and day
- delete email notifications
- delete inbound sms
- delete invitations
- delete letter notifications
- delete notifications for service and type
- delete notifications older than retention
- delete sms notifications
- delete verify codes
- deliver email
- deliver sms
- process incomplete jobs
- process job
- process returned letters list
- process ses result
- process virus scan error
- process virus scan failed
- raise alert if letter notifications still sending
- raise alert if no letter ack file
- record daily sorted counts
- remove letter jobs
- remove sms email jobs
- replay created notifications
- run scheduled jobs
- save api email
- save api sms
- save daily notification processing time
- save email
- save letter
- save sms
- send complaint
- send delivery status
- send inbound sms
- switch current sms provider on slow delivery
- tend providers back to middle
- timeout sending notifications
- update billable units for letter
- update letter notifications statuses
- update letter notifications to error
- update letter notifications to sent
- update validation failed for templated letter

## Priority queue

For tasks that should happen before other stuff, there's a priority queue. Platform admins
can set templates to use this queue.

Currently, this queue doesn't do anything special. If the normal queue is very busy, it's
possible that this queue will be faster merely because it's shorter. By the same logic, a 
busy priority queue is likely to be _slower_ than the normal queue

## Celery scheduled tasks

After scheduling some tasks, run celery beat to get them moving:

```
make run-celery-beat
```
