# TITLE:  Determine How to Handle Timezones in US Notify


| CREATED DATE | LAST UPDATED | STATUS | AUTHOR |
| :---: | :---: | :---: | :---: | :---: |
| 06/06/2023 | 11/02/2023 | Accepted | @terrazoon, @ccostino |


## CONTEXT AND PROBLEM STATEMENT

**OPEN ISSUE(S):** https://github.com/GSA/notifications-api/issues/260, along
with a related pull request: https://github.com/GSA/notifications-api/pull/272

Currently, the application converts back and forth to Eastern Time in a few
places, using utilities provided by `notifications-utils`. This adds complexity
and possible confusion since we'll actually be working over multiple timezones.

We are currently linked to timezones in the backend, and we want to unlink it,
but we quickly find places where things do not match up.


## DECISION DRIVERS

We're looking for these primary outcomes with this work:

- Find all the time-dependent pieces of the application.
- Decide what we can tackle now versus later.
- Determine what the return on this is.

We've also identified the following areas as pieces of the application and
service that could be impacted by any timezone changes:

- Reports by day (or specific month/year)
- Jobs running at a reasonable time
- Job schedules (we want users to understand when things will happen)
- Scheduling sending of messages
- UI listing of time messages were sent

Ultimately, we're looking for the least disruption possible while maximimizing
our ability to operate the service consistently with predictable results.


### SECURITY COMPLIANCE CONSIDERATIONS

None at this time, given that the nature of this work is strictly changing the
way timezones are handled in the existing application.


## CONSIDERED OPTIONS

As a team, we've gone through the following options:

- **Backend UTC, frontend explicitly ET**:  We convert the backend to UTC and
  keep the frontend as Eastern Time.

- **Backend UTC, frontend UTC**:  We convert both the backend and frontend to
  UTC time.

- **Backend UTC, frontend configurable at service level**:  We convert the
  backend to UTC and make the frontend configurable at the eservice level.

- **Backend UTC, frontend configurable at user level**:  We convert the backend
  to UTC and make the frontend configurable at the user level.

- **Backend UTC, frontend verbose (various options)**:  We convert the backend
  to UTC and strive for maximum flexibility on the frontend with a variety of
  configuration options.

For all of these options, we've settled on the need to adjust the backend
service to operate and manage timezones with UTC only.

Pros of converting the backend to UTC:

- Eliminates entire classes of bugs trying to synchronize jobs, reports,
  scheduling of sending messages, etc., and ensures things are always running
  when expected.

- This is a fairly standard industry practice when dealing with any timezone
  management in the applicationo; have the backend operate strictly with UTC
  and leave the display and formatting of timezones in local time to the client.

Cons of converting the backend to UTC:

- There's a decent amount of work involved in the conversation, and tests need
  to be updated to ensure they're accounting for the timezone change as well.

For the frontend choices we have, it comes down to level of effort, time
involved, and what is a higher priority for us now versus later.

Pros of converting parts of the frontend now:

- It provides a bit of consistency with the backend change, and accounts for the
  work now instead of later.

- It offers a level of configuration not currently available in the app, which
  would allow users to interact with and customize it in ways that better suite
  their needs and preferences.

Cons of converting parts of the frontend now:

- There is a lot of additional work involved, not all touch points are known,
  and there is a signficant effort underway at the moment to update the
  frontend design and information architecture.

- We're still not entirely sure at which level of granularity we'd like to offer
  customization, if any.


## CHOSEN OPTION:  Backend UTC, frontend explicitly ET

After talking through each of these options together as a team, we have decided
to move forward with converting the backend to UTC fully and pairing that work
with displaying ET in the frontend where need be.

Multiple team members also spoke about the benefits of storing, processing, and
managaging timezones as only UTC in the backend of the system and that it's
worth the additional work to implement.  The challenges inherent in trying to
manage timezones directly are too many and greatly increase the risk of new bugs
and undesired behavior and side-effects being introduced into the system.

Previously, using UTC in the UI as well proved that UTC is unclear to nearly all
users. ET is a more understandable and expected default.


## NEXT STEPS

With the decision to move the backend to UTC, the following actions need to be
taken:

- **Change the backend to use UTC:**  Remove all references to specific
  timezones and switch everything to use UTC.
  - Accounted for in https://github.com/GSA/notifications-api/pull/272

- **Update tests to account for the UTC change:**  All of the tests that have
  anything to do with a timezone will need to be updated to continue to work
  properly.
  - Accounted for in https://github.com/GSA/notifications-api/pull/272

We also need to update the frontend to account for these changes.  This will be
done in two parts:

1. We'll update the UI to make sure everything reflects ET where necessary for
   any timzone displays.

1. We need to create an ADR for future frontend work for how we'd like to handle
   timezones in the UI going forward.  This is currently noted in this issue:
   https://github.com/GSA/notifications-api/issues/286
