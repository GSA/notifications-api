# US Notify Architectural Decision Records (ADRs)

This sub-folder in the US Notify API project contains the bulk of our
Architectural Decision Records (henceforth referred to as ADRs) for the overall
product and service.


## What are ADRs?

ADRs serve a few purposes for our team:

- Document important decisions related to the behavior, architecture, and/or
  dependencies of the platform
- Capture the decision making process behind a change, from its initial proposal
  all the way through to its decided outcomes
- Identify alternative approaches and note why they were ultimately not chosen
- Denote who is the decision maker(s) for a change within the team

The collection of ADRs in this repository make up our architectural decision log
(ADL).  An index of the log is maintained right here in this README just below.

For more information, you can see the details in
[our first ADR](./0001-establishing-adrs-for-us-notify.md) that establishes
everything!


## When should we write an ADR?

An ADR should be written when the team is discussing any significant change to
the system that will alter its behavior, infrastructure, and/or dependencies.

We should also consider writing an ADR when we're ready to propose something
that is new to the system, e.g., adding a new feature, leveraging a new cloud
service for additional capabilities, etc.  An ADR is a great format to write a
proposal and then share it with the rest of the team to discuss it and decide
whether or not to move forward, with or without any changes.


## How are ADRs created and maintained?

First, we have an ADR template that folks can use to work off of.  The template
exists as both a GitHub issue template and a standalone Markdown file that can
be copied as needed if folks prefer to work locally first.

By following the template, we ensure that our ADRs are consistent in language
and structure.  This allows us to easily review the documentions and discuss
them as a team.  It also guarantees that the ADR has all of the required
information.

**ADRs are intended to be living documents.**  As such, it is not uncommon t
see multiple pull requests (PRs) filed to update them, especially during an
active discussion and research taking place.  This is also why there is a
*status* marker on them as a part of their metadata.


### Creating an ADR

To create a new ADR in this repository, you can do one of two things:

- Open a new GitHub issue and select the Architecture Decision Record issue type
- Clone the repo locally, create a new branch for yourself, and make a copy of
  the Markdown template.

In either scenario, check to see what the latest ADR filename is, because they
always start with a number (e.g., `0001`).  Name your ADR with a number one
after the last ADR written; if the latest ADR starts with `0021-`, your ADR
should start with `0022-`.

At this point, it is a matter of filling in the details outlined in the template
that are relevant to the ADR.


### Maintaining an ADR

If an ADR requires some updates or is ready to be accepted or rejected, you can
either edit the file directly in GitHub or create a new branch in the repo on
your local machine and make the changes necessary.

In either scenario, you'll create a pull request (PR) with your changes that
will then be ready for review from others on the team.


## Architecture Decision Log

This is the log of all of our ADRs in reverse chronological order (newest is up
top!).

- [ADR-0001](./0001-establishing-adrs-for-us-notify.md) - Establishing ADRs for US Notify