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


## How are ADRs created, reviewed, and maintained?

First, we have an ADR issue template that folks can use to start. Select the
"Create a new ADR" option when creating a new issue.

By following the template, we ensure that our ADRs are consistent in language
and structure.  This allows us to easily review the documentions and discuss
them as a team.  It also guarantees that the ADR has all of the required
information.

**ADRs are intended to be living documents.**  As such, it is not uncommon to
see multiple pull requests (PRs) filed to update them, especially during an
active discussion and research taking place.  This is also why there is a
*status* marker on them as a part of their metadata.

Once an ADR has been reviewed and is ready to be finalized (either as accepted,
rejected, or some other status), some final edits are made to update the ADR
with decision details and next steps.  After this, future PRs can be opened to
make additional updates, especially if an ADR becomes deprecated or superceded
by another one.


### Draft and Private ADRs

For ADRs that we are collaborating over in real-time or much more synchronously
as opposed to PR reviews and such, and/or storing private ADRs that we cannot
share publicly, we have an
:lock: [Architectural Decision Record Drive folder](https://drive.google.com/drive/folders/1APnbNZ81AuhZ8RFSyU5i9m_ZIetdHc-Q)
to store these documents in.

For Draft ADRs that can become **public**, once they're in a state that there
isn't as a great a need for synchronous collaboration they can be copied to a
Markdown file using the ADR template in GitHub and moved here, following the
process we have outlined in this document.

For ADRs that must remain **private**, there is a place to store them in the
aforementioned Drive folder once they're in a finalized state.  We will still
reference them in the Architectural Decision Log below, but there either won't
be links or the link will go to a :lock: *private document* instead.


### Creating an ADR

To create a new ADR in this repository, you can do one of two things:

- Open a new GitHub issue and select the "Create a new ADR" option
- Clone the repo locally, create a new branch for yourself, and make a copy of
  the Markdown template

Creating an ADR manually should be used primarily when memorializing a decision
that the team has already made. Anything requiring discussion should be created
as an issue.

We are using [some automation]([url](https://github.com/18F/adr-automation/))
to turn proposed-ADR issues into accepted-ADR documents. When an ADR is accepted,
apply the `ADR: accepted` label and close the issue. The action will open a pull
request with the document, which can then be merged.

When working locally, be sure to number your ADR based on the last ADR written;
if the latest ADR starts with `0021-`, for example, your ADR should start with
`0022-`.

At this point, it is a matter of filling in the details outlined in the template
that are relevant to the ADR.


### Reviewing an ADR

Once an ADR is created, it's time for review and discussion!  This could happen
a few ways:

- Asynchronously via comments on the issue itself
- Synchronously-ish on Slack
- Synchronously with a scheduled meeting(s) and a facilitator
- A combination of these, depending on the nature of the ADR and needs of the
  team

Whichever way is chosen, the review process should allow the team to dig into
the proposal and talk through its merits, address anything needing
clarification, discuss any potential alternatives, and develop an understanding
of the trade-offs in deciding to move forward with the proposal or not.

If it turns out that one of the alternatives proves to be a better solution, the
ADR should be updated to reflect that and a follow-up discussion and/or review
should be held to make sure everything is accurate and up-to-date.

**Please note:** Similar to sprint retrospectives, these review sessions *must*
ensure a healthy and open dialog within the team; therefore, we actively work
to promote psychological safety so that everyone and their contributions are
welcomed and respected.

As a reminder, we can reference these statements, just as we would in a sprint
retrospective:

>We are here to improve our team and our way of working incrementally over time.
>This is a safe space, where we can openly discuss anything related to the team
>or project in a [blameless manner](https://opensource.com/article/19/4/psychology-behind-blameless-retrospective).

[Retrospective Prime Directive](https://retrospectivewiki.org/index.php?title=The_Prime_Directive):

>“Regardless of what we discover, we understand and truly believe that everyone
>did the best job they could, given what they knew at the time, their skills and
>abilities, the resources available, and the situation at hand.”

*– Norm Kerth, Project Retrospectives:  A Handbook for Team Review*

An approach we can take during the discussions is to use the principles of
:lock: [The Art of Alignment](https://drive.google.com/file/d/1pPIzJG1kcnudR1HjZiB5UZgwYJ1dyetS/view?usp=share_link).
There are also other frameworks and tools for sharing proposals and achieving
consensus within a team.


### Maintaining an ADR

If an ADR requires some updates or is ready to be accepted or rejected, you can
either edit the file directly in GitHub or create a new branch in the repo on
your local machine and make the changes necessary.

In either scenario, you'll create a pull request (PR) with your changes that
will then be ready for review from others on the team.

ADR statuses can be one of the following:

- Proposed
- Accepted
- Rejected
- Deprecated
- Superseded By (new ADR number and link)

There is also a field for tracking if an ADR is implemented or not (`Yes` or
`No`).

Once the ADR itself is updated, this README also needs to be updated so that the
ADR is listed in the Architecture Decision Log just below.  This lists all of
our ADRs in reverse chronological order so we have a convenient index of them.


## Architecture Decision Log

This is the log of all of our ADRs in reverse chronological order (newest is up
top!).

|                             ADR                              |                                               TITLE                                               | CURRENT STATUS | IMPLEMENTED | LAST MODIFIED |
|:------------------------------------------------------------:|:-------------------------------------------------------------------------------------------------:|:--------------:|:-----------:|:-------------:|
| [ADR-0015](./0015-async-report-generation.md) | [Improve API stability when processing job data and generating reports](./0015-async-report-generation.md) |    Accepted    |     Yes      |  08/11/2025   |
| [ADR-0014](./0014-adr-localize-notifications-python-client.md) | [Bring in the notifications-python-client directly to the API and Admin apps](./0014-adr-localize-notifications-python-client.md) |    Accepted    |     Yes      |  06/10/2025   |
| [ADR-0013](./0013-log-debug-tags.md) | [Use of debug search tags for cloudwatch logs](./0013-log-debug-tags.md) |    Accepted    |     Yes      |  02/27/2025   |
| [ADR-0012](./0012-adr-report-generation.md) | [Optimize processing of delivery receipts](./0012-adr-report-generation.md) |    Accepted    |     Yes      |  02/12/2025   |
| [ADR-0011](./0011-adr-delivery-receipts-updates.md) | [Optimize processing of delivery receipts](./0011-adr-delivery-receipts-updates.md) |    Accepted    |     Yes      |  01/22/2025   |
| [ADR-0010](./0010-adr-celery-pool-support-best-practice.md) | [Make best use of celery worker pools](./0010-adr-celery-pool-support-best-practice.md) |    Accepted    |     Yes      |  01/07/2025   |
| [ADR-0009](./0009-adr-implement-backstopjs-to-improve-qa.md) | [Use backstopJS for QA Improvement within Admin Project](./0009-adr-implement-backstopjs-to-improve-qa.md) |    Accepted    |     Yes      |  08/27/2024   |
| [ADR-0008](./0008-adr-handle-paid-quotas-at-the-organization-level.md) | [Handle paid quotas at the organization level](./0008-adr-handle-paid-quotas-at-the-organization-level.md) |    Accepted    |     No      |  09/30/2023   |
| [ADR-0007](./0007-adr-manage-total-record-retention-dynamically.md) | [Manage total record retention dynamically](./0007-adr-manage-total-record-retention-dynamically.md) |    Accepted    |     Yes      |  11/07/203   |
|     [ADR-0006](./0006-use-for-dependency-management.md)      |         [Use `poetry` for Dependency Management](./0006-use-for-dependency-management.md)         |    Accepted    |     Yes     |  09/08/2023   |
|          [ADR-0005](./0005-agreement-data-model.md)          |                  [Agreement info in data model](./0005-agreement-data-model.md)                   |    Accepted    |     No      |  07/05/2023   |
|   [ADR-0004](./0004-designing-pilot-content-visibility.md)   |        [Designing Pilot Content Visibility](./0004-designing-pilot-content-visibility.md)         |    Proposed    |     No      |  06/20/2023   |
|    [ADR-0003](./0003-implementing-invite-expirations.md)     |         [Implementing User Invite Expirations](./0003-implementing-invite-expirations.md)         |    Accepted    |     No      |  09/15/2023   |
|        [ADR-0002](./0002-how-to-handle-timezones.md)         |        [Determine How to Handle Timezones in US Notify](./0002-how-to-handle-timezones.md)        |    Accepted    |     Yes     |  06/15/2023   |
|    [ADR-0001](./0001-establishing-adrs-for-us-notify.md)     |           [Establishing ADRs for US Notify](./0001-establishing-adrs-for-us-notify.md)            |    Accepted    |     Yes     |  06/15/2023   |
