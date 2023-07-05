# TITLE: Agreement info in data model


| CREATED DATE | LAST UPDATED | STATUS | AUTHOR | STAKEHOLDERS |
| :---: | :---: | :---: | :---: | :---: |
| 06/21/2023 | 07/05/2023 | Accepted | @stvnrlly, @ccostino | @GSA/notify-contributors |


## CONTEXT AND PROBLEM STATEMENT

**OPEN ISSUE(S):** https://github.com/GSA/notifications-api/issues/141, https://github.com/GSA/notifications-admin/issues/53, https://github.com/GSA/notifications-admin/issues/51 

We will be entering into Memoranda of Understanding (MOU) and Interagency
Agreements (IAA) with partner agencies. Data from those agreements will be
important for application function.

Unlike the UK version of the application, users will not be able to complete a
self-service in-app agreement process. Our agreement process requires that
documents be “signed” outside of the application and (especially in the case of
an IAA) needs to happen with specific forms that have historically proven
difficult to automate.

Inside the application, we’ll want to know information about the partner as well
as information necessary to avoid overspending the account.

This information includes:
- Agreement identifier
- Agreement type (MOU or IAA)
- Agreement partner name
- Agreement status
- Agreement start datetime (known as period of performance)
- Agreement end datetime (known as period of performance)
- Agreement URL (where it is in Google Drive)
- Budget amount (*not* message limit)


## DECISION DRIVERS

An implementation should address these needs:

- The need for multiple agreements per partner over time
- The information and tools to stop sending before overspending
- The ability to connect data to organization and service models

This is a minimal implementation of agreement data. It's quite possible that 
it will change and expand over time, but those needs are not yet clear.

Because we will continue to have the actual agreement docs safely in Google 
Drive, this implementation does not need to be a source of truth and does not 
need to retain history over time.


### SECURITY COMPLIANCE CONSIDERATIONS

We will need to take care about permissions to change this data. Existing 
permissions are fairly binary: you are a user or you are an admin. We should 
consider whether that's still sufficient or if an in-between role would be 
useful.


## CONSIDERED OPTIONS

As a team, we've gone through the following options:

- Add an Agreement model: a new class in `models.py` with the relevant fields.
  - Pros:
    - Separates agreements from the orgs, since they may change separately
    - Multiple agreement-like models might be confusing, this avoids that
  - Cons:
    - Groups IAA and MOU together, which makes validation at the model level
      harder and, in turn, makes it easier to break validation logic elsewhere
      in the application

- Add MOU and IAA models: two new classes in `models.py` with the same fields 
  but different configurations.
  - Pros:
    - Cleanest representation of the real world
    - Allows SQL-level support for required/unique fields 
  - Cons:
    - Most complex data model

- Add agreement info to Organization model: no new classes, just a combination
  of new fields and properties.
  - Pros:
    - No added model complexity
  - Cons:
    - Doesn’t directly allow for history


## CHOSEN OPTION: Add an Agreement model

By adding an Agreement model, we’ll allow flexibility in the interaction between
agreements and organizations but stop short of attempting to recreate the full
complexity of agreements in our data model.

If we later find that it’s necessary to separate MOU and IAA agreements, we
should be able to perform a migration.


### Consequences

- Positive
  - We’ll gain more granular control over message limits for paid (IAA)
    agreements
  - We can offer more agreement transparency to users. For example, identifying 
    agreements that will need renewal

- Negative
  - We’re adding some complexity to the data model
  - We know that this implementation is an MVP and thus might have rough edges
  - Manual work is necessary to keep agreements in sync with the real-world
    process


## VALIDATION AND NEXT STEPS

This process includes adding the new model and updating the existing models to 
use them.

1. Add the new model:
  - Add Agreement to models.py with the fields identified above
  - Create migration to add/update table

2. Update the Organisation model:
  - Add one-to-many field linking one Organisation to multiple Agreements
  - Add model property to convert budget amount into message limit
  - Add model property to provide remaining budget based on sent messages
  - Add model property about whether free tier or not
  - Add model property for free tier usage (retrieve messages sent in a year)

This will set up a new system, but stops short of connecting agreements to the 
services actually sending the messages. This approach will be laid out in a 
forthcoming ADR about managing message limits.
