# Deploying

We deploy automatically to cloud.gov for demo and staging environments.

Deployment to staging runs via the [base deployment action](../.github/workflows/deploy.yml) on GitHub, which pulls credentials from GitHub's secrets store in the staging environment.

Deployment to demo runs via the [demo deployment action](../.github/workflows/deploy-demo.yml) on GitHub, which pulls credentials from GitHub's secrets store in the demo environment.

The [action that we use](https://github.com/18F/cg-deploy-action) deploys using [a rolling strategy](https://docs.cloudfoundry.org/devguide/deploy-apps/rolling-deploy.html), so all deployments should have zero downtime.

The API has 2 deployment environments:

- Staging, which deploys from `main`
- Demo, which deploys from `production`

In the future, we will add a Production deploy environment, which will deploy in parallel to Demo.

Configurations for these are located in [the `deploy-config` folder](../deploy-config/).

In the event that a deployment includes a Terraform change, that change will run before any code is deployed to the environment. Each environment has its own Terraform GitHub Action to handle that change.

Failures in any of these GitHub workflows will be surfaced in the Pull Request related to the code change, and in the case of `checks.yml` actively prevent the PR from being merged. Failure in the Terraform workflow will not actively prevent the PR from being merged, but reviewers should not approve a PR with a failing terraform plan.

## Egress Proxy

The API app runs in a [restricted egress space](https://cloud.gov/docs/management/space-egress/).
This allows direct communication to cloud.gov-brokered services, but
not to other APIs that we require.

As part of the deploy, we create an
[egress proxy application](https://github.com/GSA/cg-egress-proxy) that allows traffic out of our
application to a select list of allowed domains.

Update the allowed domains by updating `deploy-config/egress_proxy/notify-api-<env>.allow.acl`
and deploying an updated version of the application throught he normal deploy process.

## Sandbox environment

There is a sandbox space, complete with terraform and `deploy-config/sandbox.yml` file available
for experimenting with infrastructure changes without going through the full CI/CD cycle each time.

Rules for use:

1. Ensure that no other developer is using the environment, as there is nothing stopping changes from overwriting each other.
1. Clean up when you are done: 
    - `terraform destroy` from within the `terraform/sandbox` directory will take care of the provisioned services
    - Delete the routes shown in `cf routes`
    - Delete the apps shown in `cf apps`
    - Delete the service keys for any remaining space deployers, likely `cf dsk <space-deployer> service-account-key`
    - Delete the space deployers still shown in `cf services`

### Deploying to the sandbox

1. Set up services:
    ```
    $ cd terraform/sandbox
    $ ../create_service_account.sh -s notify-sandbox -u <your-name>-terraform -m > secrets.auto.tfvars
    $ terraform init
    $ terraform plan
    $ terraform apply
    ```
1. start a pipenv shell as a shortcut to load `.env` file variables: `$ pipenv shell`
1. Deploy the application:
  ```
  cf push --vars-file deploy-config/sandbox.yml --var AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID --var AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY
  ```
