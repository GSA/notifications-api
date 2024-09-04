# Adopting BackstopJS for Enhanced QA in Admin Project

Status: Proposed
Date: August 27th, 2024

### Context
We're looking to integrate BackstopJS, a visual regression testing tool, into our Admin UI project to improve QA and keep our UI consistent. This tool will help catch visual bugs early and make sure our design stays on track. We considered several options: deferring the integration, minimal integration with our current tools, full integration using Docker, and an optional testing setup. The goal is to find a balance between ease of use for developers and thorough testing while making sure the integration fits well with our current CI/CD pipeline.

### Decision
We decided to integrate BackstopJS as an optional part of our workflow. This means developers can run visual regression tests when they think it's needed, using specific Gulp commands. By doing this, we keep the process flexible and minimize friction for those who are new to the tool. We’ll also provide clear documentation and training to help everyone get up to speed. If this approach works well, we might look into making these tests a regular part of our process down the road by integrating into the CI/CD process.


### Consequences
With this decision, we make it easier for developers to start using BackstopJS without introducing a complicated library to them. This should help us catch more visual bugs and keep our UI consistent over time. The downside is that not everyone may run the tests regularly, which could lead to some missed issues. To counter this, documentation will be created to help developers understand how to best use BackstopJS. The initial setup will take some time, but since it matches the tools we already use, it shouldn’t be too much of a hassle. We’re also thinking about integrating BackstopJS into our CI/CD pipeline more fully in the future, so we won’t have to rely on local environments as much.

### Author
@alexjanousekGSA

### Stakeholders

### Next Steps
- Start setting up BackstopJS with Gulp.
- Create documentation and training materials.
- Hold training sessions to introduce developers to BackstopJS.
- Keep an eye on how well the integration is working and get feedback from the team.
- Make adjustments as needed based on what we learn and begin implementing into CI/CD process.
