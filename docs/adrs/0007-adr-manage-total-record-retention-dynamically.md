# ADR: Manage total record retention dynamically

Status: Accepted
Date: 09/27/23

### Context

Currently, we have a global maximum for messages sent per day. This is designed to limit the amount of PII that we're holding at any given time. That limit is a Redis counter that auto-increments with each message sent.

However, since we've also implemented #318 to immediately scrub and archive successful messages, the Redis counter and the records stored will be out of sync. We can expect our number of records with PII to be much lower.

To provide senders with more flexibility, our limit should be based on the number of records in the `notifications` table.

### Decision

We will check the total count of the `notifications` table inside of `check_service_over_total_message_limit()`. This is located in `/app/notifications/validators.py`. This may require a new DAO function to access the data.

We also considered:

- Adding more checks to validate whether the number of messages in a CSV would go over the limit, but this doesn't seem necessary (yet).
- Creating a job to cache the number of records in a Redis key. This would save some database calls while sending messages, but the performance tradeoff is probably not worth the loss of precision.


### Consequences

- We will have more database calls while sending messages.
- It's possible for message-sending to get blocked during a batch until the database is cleaned.

### Author

@stvnrlly & @ccostino

### Stakeholders

_No response_

### Next Steps

#463
