# Use `poetry` for dependency management

Date: 2023-09-08

### Status

Implemented

### Context

Our initial decision to use  was primarily driven by [built-in support in Cloud Foundry](https://docs.cloudfoundry.org/buildpacks/python/index.html#pipenv). In practice, we have found that we still need to export the requirements file as part of the build process, removing the benefit.

Meanwhile, `poetry` appears to be the informal standard around TTS. It's relatively simple for a dev to switch between them, but we do value consistency across the organization.

### Decision

Let's use `poetry`.

### Consequences

We expect this to be a one-time cost.

### Author

@stvnrlly


### Next Steps

We will need to:

- Convert to `poetry`
- Convert our CI/CD processes
- Ensure [proper Dependabot configuration](https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file)
- Update developer documentation
- Get familiar with the tool
