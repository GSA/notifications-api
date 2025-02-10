# Make best use of celery worker pools

Status: Accepted
Date: 7 January 2025

### Context
Our API application started with initial celery pool support of 'prefork' (the default) and concurrency of 4.  We continuously encountered instability, which we initially attributed to a resource leak.  As a result of this we added the configuration `worker-max-tasks-per-child=500` which is a best practice.  When we ran a load test of 25000 simulated messages, however, we continued to see stability issues, amounting to a crash of the app after 4 hours requiring a restage.  Based on running `cf app notify-api-production` and observing that `cpu entitlement` was off the charts at 10000% to 12000% for the works, and after doing some further reading, we came to the conclusion that perhaps `prefork` pool support is not the best type of pool support for the API application.

The problem with `prefork` is that each process has a tendency to hang onto the CPU allocated to it, even if it is not being used.  Our application is not computationally intensive and largely consists of downloading strings from S3, parsing the strings, and sending them out as SMS messages.   Based on the determination that our app is likely I/O bound, we elected to do an experiment where we changed pool support to `threads` and increased concurrency to `10`.   The expectation is that memory usage will decrease and CPU usage will decrease and the app will not become unavailable.

### Decision

We decided to try to the 'threads' pool support with increased concurrency.

### Consequences

We saw an immediate decrease in CPU usage of about 70% with no adverse consequences.

### Author
@kenkehl

### Stakeholders
@ccostino
@stvnrlly

### Next Steps
- Run an after-hours load test with production configured to --pool=threads and --concurrency=10 (concurrency can be cautiously increased once we know it works)
