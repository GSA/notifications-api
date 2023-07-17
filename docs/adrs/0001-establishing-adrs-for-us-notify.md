# TITLE:  Establishing ADRs for US Notify


| CREATED DATE | LAST UPDATED | STATUS | AUTHOR | STAKEHOLDERS |
| :---: | :---: | :---: | :---: | :---: |
| 06/01/2023 | 06/15/2023 | Accepted | @ccostino | @stvnrlly |


## CONTEXT AND PROBLEM STATEMENT

**OPEN ISSUE:** https://github.com/GSA/notifications-api/issues/282

As a developer of the system, I'd like to be able to keep track of system
architecture decisions and understand why they were made, including what
trade-offs and alternatives might have existed at the time. I'd also like to
keep track of these in a place that I can refer back to later for historical
context.


## DECISION DRIVERS

These are the key considerations for creating ADRs for US Notify:

- We'd like to establish a decision-making framework for future proposals to
  improve or change the product/service.

- We'd like to document the outcome of our decisions and include the rationale
  behind them to know what we've already considered previously.

- In the spirit of open source and collaboration, we'd like to make our
  decisions as open as possible, but recognize there are times when we cannot;
  in those cases, we'll follow the same process but in a private location.

- We need to make sure we're accounting for any security compliance concerns
  and considerations ahead of time, while we're actively thinking about how to
  architect and implement a thing instead of after the fact.


### SECURITY COMPLIANCE CONSIDERATIONS

- Documenting architectural details in the open
  - We should err on the side of documenting in the open whenever possible, but
    some details we will not be able to share.  We should create issues for
    those cases to note the work happening in a private space.

- Sensitive information must not be shared
  - We need to be judicious in not documenting any sensitive bits of information
    like account credentials or passwords, environment variable values, etc.


## CONSIDERED OPTIONS

- **Architectural Decision Records:**  A common document format for capturing
  architectural decisions that many development teams have adopted in recent
  years, including at large technology companies such as
  [GitHub](https://adr.github.io/) and [Amazon Web Services](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/welcome.html) and TTS' own [18F](https://18f.gsa.gov/2021/07/06/architecture_decision_records_helpful_now_invaluable_later/).

  - Pros:
    - Well-known format that has many example templates to choose from
    - Can be as simple or complex as desired
    - Additional tooling exists to help manage ADRs
    - ADRs are committed to and live with the code itself
    - Easy to link to other parts of the repo

  - Cons:
    - Takes a bit of prep to setup; best supported with a template to copy from
    - Setting up additional tooling takes time and requires additional
      maintenance
    - Requires some training for folks not already familiar with ADRs
    - Easy to go overboard with
    - Requires being mindful of what can live in the public space vs. not

- **Google Docs in Google Drive:**  Writing up notes docs in Google Drive with
  Google Docs.

  - Pros:
    - Simple and lightweight to do
    - Possible to setup a doc template to create from, if desired
    - Ability for team members to collaborate in real-time with each other
    - Useful for documenting things that cannot be public
    - Access to tools/features like a spellchecker

  - Cons:
    - Google Drive organization is difficult; keeping track of documents
      can become hard
    - Easy to not follow a standard and agreed upon format
    - Not open to the public for things that can be shared publicly
    - Documentation does not live directly with the code

- **GitHub Issues and/or Wiki:**  Writing up notes and decisions directly in
  GitHub issues and/or the wiki associated with a repo.

  - Pros:
    - Simple and lightweight to do
    - Possible to configure an issue template to create from, if desired
    - Easy to link to related issues, wiki pages, etc.

  - Cons:
    - Documentation lives in a GitHub itself, not the code repository directly;
      therefore, it's not portable
    - Easy to not follow a standard and agreed upon format if no template is
      provided
    - Requires being mindful of what can live in the public space vs. not


## CHOSEN OPTION:  Architectural Decision Records

Our team has chosen to adopt Architectural Decision Records going forward for
any decisions that need to be proposed or discussed that will have a significant
impact on the platform.

By documenting our changes in this fashion, it will improve our team's
development practices and software quality in a few ways:

- Encourage us to slow down and think through a new change, especially anything
  of significance
- Hold us accountable to each other in soliciting feedback for our work and
  engaging in discussions earlier in the process of building something
- Provide a mechanism to propose ideas for changes and improvements to the
  system that is also archived with the code itself
- Bake security compliance considerations into our development process from the
  start, ensuring they are not just after-thoughts once something is completed

ADRs have a wealth of material and support to draw from, other teams across TTS
are already using them (e.g., cloud.gov, a variety of 18F projects, and others),
and other large organizations, including GitHub and Amazon, have also adopted
them.  Some example material to reference:

- [How to Create ADRs - and How Not To](https://www.ozimmer.ch/practices/2023/04/03/ADRCreation.html)
- [The Markdown ADR (MADR) Template Explained and Distilled](https://www.ozimmer.ch/practices/2022/11/22/MADRTemplatePrimer.html)
- [The Ultimate Guide to Architectural Decision Records](https://betterprogramming.pub/the-ultimate-guide-to-architectural-decision-records-6d74fd3850ee)


### Consequences

- Positive
  - Formal decision documentation and history
  - Proactive security compliance considerations in the decision-making process
  - Accepted means of proposing new ideas for the future

- Negative
  - A bit of a learning curve in making sure all team members are aware and
    brought up to speed of what ADRs are
  - Some configuration and set up required; mainly new templates, though one is
    provided with this proposal


## VALIDATION AND NEXT STEPS

@stvnrlly and I went over this proposal and have worked together to get it in
the shape it needs to be for the team to work off of.  The corresponding ADR
README.md that was a part of the original pull request was also refined to make
sure it contains all relevant information and instructions.
