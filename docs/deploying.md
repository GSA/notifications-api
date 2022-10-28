# Deploying

We deploy automatically to cloud.gov for production and staging environments.

Deployment runs via the [deployment action](../.github/workflows/deploy.yml) on GitHub, which pulls credentials from GitHub's secrets store.

The [action that we use](https://github.com/18F/cg-deploy-action) deploys using [a rolling strategy](https://docs.cloudfoundry.org/devguide/deploy-apps/rolling-deploy.html), so all deployments should have zero downtime.

The API has 2 deployment environments:

- Production, which deploys from `main`
- Staging, which does not, in fact, exist

Configurations for these are located in [the `deploy-config` folder](../deploy-config/).

In the event that a deployment includes a Terraform change, that change will run before any code is deployed to the environment. Each environment has its own Terraform GitHub Action to handle that change.

Failures in any of these GitHub workflows will be surfaced in the Pull Request related to the code change, and in the case of `checks.yml` actively prevent the PR from being merged. Failure in the Terraform workflow will not actively prevent the PR from being merged, but reviewers should not approve a PR with a failing terraform plan.