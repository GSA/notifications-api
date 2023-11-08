# TITLE:  Implementing User Invite Expirations


| CREATED DATE | LAST UPDATED | STATUS | AUTHOR | STAKEHOLDERS |
| :---: | :---: | :---: | :---: | :---: |
| 06/06/2023 | 11/08/2023 | Accepted | @ccostino | @GSA/notify-contributors |


## CONTEXT AND PROBLEM STATEMENT

**OPEN ISSUE(S):** https://github.com/GSA/notifications-admin/issues/96

We've run into a situation where we want to re-invite users when their previous
invites have expired.  However, we're not currently able to do that because
there is no mechanism in the app (specifically the API and the data model) to
support expired invites.

Right now, users who are invited to the system receive an email invitation that
includes a note that the invitation will expire after 24 hours.

However, on the backend side of things, no such expiration exists.  Instead,
there is a scheduled job that runs every 66 minutes to check for all
`InvitedUser` objects that are older than 2 days and deletes them.

([Issue #96 in `notifications-admin`](https://github.com/GSA/notifications-admin/issues/96)
has more specific details.)


## DECISION DRIVERS

We'd like to adjust the API and data model so that invited users are no longer
deleted from the system and are instead tracked as active or expired.  When an
invite is expired, we'd like to be able to show that in the invited users
screen and provide the ability re-invite the person.


### SECURITY COMPLIANCE CONSIDERATIONS

The system currently has a data model for capturing an invited user
(`InvitedUser`), which is based on an authorized user of the system having the
permission to invite others to it.

These changes should not deviate from the existing structures and contraints
that are already in place, which prevent the following:

- Unauthorized users from accessing the system
- Users without the proper permissions from inviting others


## CONSIDERED OPTIONS

This is the approach we've considered for implementing this change:

- **Adjust `InvitedUser` management in the API:**  Instead of deleting
  `InvitedUser` objects, we manage them instead and track their `created_at`
  dates for when they need to expire.  This would involve the following
  potential changes:

  - Change the `delete_invitations` scheduled job to `expire_invitations` and
    change its behavior to check for `InvitedUser` objects that are older than
    24 hours and change the status type to `expired`.

  - Add an additional `INVITE_EXPIRED` status to the API and include it in the
    `INVITED_USER_STATUS_TYPES` enum.  This will be necessary for future UI
    changes.

  - Make sure the API responses that provided `InvitedUser` objects/data
    included the new `expired` status.

  - Update all tests related to `InvitedUsers` to account for the new behavior;
    this may require making a new test or two to check explicitly for the new
    `expired` status.

  The pros in making this change:

  - This will enable us to support expiring invites in the system, including
    frontend changes to enable seeing and managing expired invites.

  The cons in making this change:

  - Updated the tests might be a bit challenging depending on how many there are
    (especially any related to scheduled jobs).


## PROPOSED OPTION:  Adjust `InvitedUser` management in the API

I am proposing we adjust the `InvitedUser` management in the API and get these
updates in place first for future UI changes, because without them we cannot
display any expired invites nor offer a way of managing them or providing an
option to re-invite folks.

After looking through the code and researching how the existing user invite
flow works, these changes seem straight-forward and would yield us a lot of
value for the effort.


### Consequences

- Positive
  - Allows us to support expired invites
  - We could allow for custom expiration periods (either now or in the future)
  - Provides the mechanisms needed in the frontend to display and manage
    expired invites

- Negative
  - We might end up having to adjust a lot of tests; that's currently unclear.


## VALIDATION AND NEXT STEPS

Once a decision is made though, a seperate issue should be written up for the
API changes that need to take place, and then follow-on work will be needed on
the admin side in https://github.com/GSA/notifications-admin/issues/96 to make
the UI adjustments.
