# TITLE:  Creating a Static Docs Subdomain


| CREATED DATE | LAST UPDATED | STATUS | IMPLEMENTED | AUTHOR | STAKEHOLDERS |
| :---: | :---: | :---: | :---: | :---: |
| 08/15/23 | NA | Proposed | No | @tdlowden | @stvnrlly |


## CONTEXT AND PROBLEM STATEMENT

**OPEN ISSUE(S):** Link(s) to related issue(s) here, if applicable.

The Notify.gov application currently houses guidance and documentation within the main production domain, which at time of writing is beta.notify.gov. Additionally, during initial launch, that content is only visible to logged-in users. The structure of those pages relies heavily on application templates and being dynamically rendered. In the future, a documentation subdomain could house application-related docs, broader notifications guidance, a blog, or otherwise. Creating this as a static jekyll-like site would eliminate code from the application base, allow more team members to feel comfortable editing content, and also provide a `preview` option when creating PRs.


## DECISION DRIVERS

List anything that plays a major role in making a decision here.  These could
be one or more of the following:

### Desired Qualities
- static site
- previews available

### Desired Outcomes
- more team members contributing
- less complicated bug fixes/changes

### Primary concerns
- Expanding beyond the single landing page will require completing all the areas of the `DLP-Launch Checklist`, which can present extra resource burden
- The new pages may need to be viewed and approved by GSA's Office of Strategic Communications, which could be a long process

### Constraints
- Approvals from OSC
- 


### SECURITY COMPLIANCE CONSIDERATIONS

Because we work in a regulated space with many compliance requirements, we need
to make sure we're accounting for any security concerns and adhering to all
security compliance requirements.  List them in this section along with any
relevant details:

- Security concern 1
  - Concern detail 1
  - Concern detail 2
  - Concern detail ...

- Security concern 2
  - Concern detail 1
  - Concern detail 2
  - Concern detail ...


## CONSIDERED OPTIONS

List all options that have either been discussed or thought of as a potential
solution to the context and problem statement.  Include any pros and cons with
each option, like so:

- **Name of first option:**  A brief summary of the option.
  - Pros:
    - Pro 1
    - Pro 2
    - Pro ...

  - Cons:
    - Con 1
    - Con 2
    - Con ...

- **Name of second option:**  A brief summary of the option.
  - Pros:
    - Pro 1
    - Pro 2
    - Pro ...

  - Cons:
    - Con 1
    - Con 2
    - Con ...


## PROPOSED OR CHOSEN OPTION:  Proposed/Chosen Option Title Here

Summarize the decision for the proposed/chosen option here.  Be as concise and
objective as possible while including all relevant details so that a clear
justification is provided.  Include a list of consequences for choosing this
option, both positive and negative:


### Consequences

- Positive
  - Positive consequence 1
  - Positive consequence 2
  - Positive consequence ...

- Negative
  - Negative consequence 1
  - Negative consequence 2
  - Negative consequence ...


## VALIDATION AND NEXT STEPS

This section likely won't be filled out until a decision has been made by the
team and the ADR is accepted.  If this comes to pass, then write up the criteria
that would ensure this ADR is both implemented and tested correctly and
adequately.  This could be a short summary and/or a list of things:

- **Criterion name 1:**  Description of criterion 1
  - Requirement or action 1
  - Requirement or action 2
  - Requirement or action ...

- **Criterion name 2:**  Description of criterion 2
  - Requirement or action 1
  - Requirement or action 2
  - Requirement or action ...

Lastly, include a link(s) to an issue(s) that represent the work that will
take place as follow-ups to this ADR.
