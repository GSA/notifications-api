# Optimize processing of delivery receipts

Status: Accepted
Date: 22 January 2025

### Context
Our original effort to get delivery receipts for text messages was very object oriented and conformed to other patterns in the app.  After an individual message was sent, we would kick off a new task on a delay, and this task would go search the cloudwatch logs for the given phone number.
On paper this looked good, but when one customer did a big send of 25k messages, we realized suddenly this was a bad idea.  We overloaded the AWS api call and got massive throttling as a result.  Although we ultimately did get most of the delivery receipts, it took hours and the logs were filled with errors.

In refactoring this, there were two possible approaches we considered:

1. Batch updates in the db (up to 1000 messages at a time).  This involved running update queries with case statements and there is some theoretical limit on how large these statements can get and still be efficient.

2. bulk_update_mappings().   This would be a raw updating similar to COPY where we could do millions of rows at a time.

### Decision

We decided to try to use batch updates.  Even though they don't theoretically scale to the same level as bulk_update_mappings(), our app has a potential problem with using bulk_update_mappings().  In order for it to work, we would need to know the "id" for each notification, which is the primary key into the notifications table.  We do NOT know the "id" when we process the delivery receipts.  We do know the "message_id", but in order to get the "id" we would either have to a select query, or we would have to maintain some mapping in redis, etc.

It is not clear, given the extra work necessary, that bulk_update_mappings() would be greatly superior to batch updates for our purposes.  And batch updates currently allow us to scale at least 100x above where we are now.

### Consequences

Batch updates greatly cleaned up the logs (no more errors for throttling) and reduced CPU consumption.  It was a very positive change.

### Author
@kenkehl

### Stakeholders
@ccostino
@stvnrlly
