# Adopting BackstopJS for Enhanced QA in Admin Project

Status: Accepted
Date: September 5th, 2024

### Context
We're looking to integrate BackstopJS, a visual regression testing tool, into our Admin UI project to improve QA and keep our UI consistent. This tool will help catch visual bugs early and make sure our design stays on track. We considered several options: deferring the integration, minimal integration with our current tools, full integration using Docker, and an optional testing setup. The goal is to find a balance between ease of use for developers and thorough testing while making sure the integration fits well with our current CI/CD pipeline.

### Decision
We decided to integrate BackstopJS as an optional part of our workflow. This means developers can run visual regression tests when they think it's needed, using specific Gulp commands. By doing this, we keep the process flexible and minimize friction for those who are new to the tool. We'll also provide clear documentation and training to help everyone get up to speed.

Once this is working well for folks locally, we'll begin incorporating these steps as an additional part of our CI/CD process and add them as a new separate job, similar to how end-to-end tests were added.  We'll first add this in as an informational only run that simply reports the results but doesn't prevent any work from going through.

After we've had a bit of time to test the workflow and make sure everything is working as expected, we'll change the workflow to make it required.  This will cause a PR, merge, or deploy to fail or not proceed if any regressions are detected, at which point someone will have to investigate and see if something was missed or a fix is needed for the test(s)/check(s) based on intentional changes.

### Consequences
With this decision, we make it easier for developers to start using BackstopJS without introducing a complicated library to them. This should help us catch more visual bugs and keep our UI consistent over time. The downside is that not everyone may run the tests regularly, which could lead to some missed issues. To counter this, documentation will be created to help developers understand how to best use BackstopJS. The initial setup will take some time, but since it matches the tools we already use, it shouldn’t be too much of a hassle. We’re also thinking about integrating BackstopJS into our CI/CD pipeline more fully in the future, so we won’t have to rely on local environments as much.

### Author
@alexjanousekGSA

### Stakeholders
@ccostino
@stvnrlly

### Next Steps
- Start setting up BackstopJS with Gulp.
- Create documentation and training materials.
- Hold training sessions to introduce developers to BackstopJS.
- Keep an eye on how well the integration is working and get feedback from the team.
- Make adjustments as needed based on what we learn and begin implementing into CI/CD process.
