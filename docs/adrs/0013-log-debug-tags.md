# Use of debug search tags for cloudwatch logs

Status: Accepted
Date: 27 February 2025

### Context

We encountered some recurrent problems in specific parts of the code that re-occurred regularly.

We found it hard to debug these issues searching through cloudwatch logs as a particular issue
tends to be exploded into multiple log lines, and these lines are not even time sorted by default
so it can get quite hard on the eyes and test one's patience to debug this way.

### Decision

We decided to start using unique tags for individual issues so we could quickly search for related
groups of log lines.  This worked fairly well and even though some of these issues at long last
have been resolved, it might be worthwhile to continue this debugging pattern.

### Consequences

Here are the existing tags and what they are used for:

#notify-debug-admin-1200: job cache regeneration
#notify-debug-admin-1701: wrong sender phone number
#notify-debug-admin-1859: job creation time reset due to strange SqlAlchemy constructor issue setting wrong created_at time
#notify-debug-api-1385: a separate identify to resolve the wrong sender phone number issue
#notify-debug-s3-partitioning: modify s3 partitioning in line with best aws practices
#notify-debug-validate-phone-number: experimental code to try to validate phone numbers with aws pinpoint




### Author
@kenkehl

### Stakeholders
@ccostino
