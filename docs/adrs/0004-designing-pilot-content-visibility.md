# TITLE: Designing Pilot Content Visibility
| CREATED DATE | LAST UPDATED | STATUS | IMPLEMENTED |AUTHOR |STAKEHOLDERS |
| :---: | :---: | :---: | :---: | :---: |:---: |
| 06/20/2023 | 06/20/2023| Proposed| No | @tdlowden | @GSA/notify-contributors |

## CONTEXT AND PROBLEM STATEMENT
**OPEN ISSUE(S):** https://github.com/GSA/notifications-admin/issues/539, https://github.com/GSA/notifications-admin/issues/521, https://github.com/GSA/notifications-admin/issues/566

The initial launch of the beta.notify.gov site requires minimal public-facing content and must remove self-service account creation from the general public, as per communications oversight within TTS.

## DECISION DRIVERS

### Desired outcomes:
- A clean, informative landing page at beta.notify.gov that allows for closed pilot partners to access the application
- No ability for members of the public to create an account or view "how-to" documentation

### Primary concerns:
- Removing the self-sevice option altogether creates more work on the team members, who have to create an account/service
- Removing the self-service option obviates the initial service creator from progressing through the `service creation wizard` content
- LOE to make currently publicly visible documentation only accessible after login

## SECURITY COMPLIANCE CONSIDERATIONS
Because we work in a regulated space with many compliance requirements, we need to make sure we're accounting for any security concerns and adhering to all security compliance requirements. List them in this section along with any relevant details:

**Security concern**

N/A

## CONSIDERED OPTIONS
List all options that have either been discussed or thought of as a potential solution to the context and problem statement. Include any pros and cons with each option, like so:

### Option 1: A minimal landing page with only a short info paragraph, a closed pilot statement, and sign-in button, completely removing the ability to create a service except if done by a Studio team member. All other pages are only accessible after login.

**Pros:**

- Simplest and least amount of content (ergo, requires least review/approval)
- No need to scope a gated self-service solution

**Cons:**

- `Service creation wizard` content is not seen by pilot users
- More work on Studio team to construct a process to get pilot partners initial account access/service creation

### Option 2: A landing page with sign-in button, pilot statement, and a small amount of "marketing" type content, completely removing the ability to create a service except if done by a Studio team member. All other pages are only accessible after login.

**Pros:**

- Allows for public vistors to know more about what the product is intended to do
- No need to scope a gated self-service solution

 **Cons:**

- `Service creation wizard` content is not seen by pilot users
- More work on Studio team to construct a process to get pilot partners initial account access/service creation
- More content to review by oversight teams

### Option 3: A minimal landing page that offers a sign-in button AND a field to input a pilot invite code, which would allow a user to then self-service create an account and initial service. All other pages are only accessible after login.

**Pros:**

- Invited users would go throught the `service creation wizard` flow and content
- A Studio team member would not need to create the initial account/service

**Cons:**

- Scoping and implementing an invite code system could cost many developer hours
- The action of creating an invite code for a user may end up being as burdensome as creating the initial account/service, nullifying the team time saved

## PROPOSED OR CHOSEN OPTION: Option 2
Option 2 provides the most benefit with least Studio work required. When weighing the value of the `service creation wizard` content/flow, we considered that it is 1. ephemeral (users can only access it once) and 2. limited to the service creator, rather than all team members. For the potential work to devise an invite code option, it did not feel that the benefit of the `wizard` outweighed the cost. Additionally, we resolve to explore replicating the `wizard` content/flow into another part of the site that can be accessed as frequently as necessary, and by all users of the application.

## VALIDATION AND NEXT STEPS
TK TK
