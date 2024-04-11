# Terraform

This directory holds the Terraform modules for maintaining Notify.gov's infrastructure. You can [read about the structure](#structure) or [get set up to develop](#retrieving-existing-bucket-credentials).

## Retrieving existing bucket credentials

:green_book: New developers start here!

Assuming [initial setup](#initial-setup) is complete &mdash; which it should be if Notify.gov is online &mdash; Terraform state is stored in a shared remote backend. If you are going to be writing Terraform for any of our deployment environments you'll need to hook up to this backend. (You don't need to do this if you are just writing code for the `development` module, becase it stores state locally on your laptop.)

1. Enter the bootstrap module with `cd bootstrap`
1. Run `./import.sh` to import the bucket containing remote terraform state into your local state
1. Follow instructions under [Use bootstrap credentials](#use-bootstrap-credentials)

### Use bootstrap credentials

1. Run `./run.sh show -json`.
1. In the output, locate `access_key_id` and `secret_access_key` within the `bucket_creds` resource. These values are secret, so, don't share them with anyone or copy them to anywhere online.
1. Add the following to `~/.aws/credentials`:
    ```
    [notify-terraform-backend]
    aws_access_key_id = <access_key_id>
    aws_secret_access_key = <secret_access_key>
    ```
1. Check which AWS profile you are using with `aws configure list`. If needed, use `export AWS_PROFILE=notify-terraform-backend` to change to the profile and credentials you just added.

These credentials will allow Terraform to access the AWS/Cloud.gov bucket in which developers share Terraform state files. Now you are ready to develop Terraform using the [Workflow for deployed environments](#workflow-for-deployed-environments).

## Initial setup

These instructions were used for deploying the project for the first time, years ago. We should not have to perform these steps again. They are provided here for reference.

1. Manually run the bootstrap module following instructions under [Terraform State Credentials](#terraform-state-credentials)
1. Setup CI/CD Pipeline to run Terraform
    1. Copy bootstrap credentials to your CI/CD secrets using the instructions in the base README
    1. Create a cloud.gov SpaceDeployer by following the instructions under [SpaceDeployers](#spacedeployers)
    1. Copy SpaceDeployer credentials to your CI/CD secrets using the instructions in the base README
1. Manually Running Terraform
    1. Follow instructions under [Workflow for deployed environments](#workflow-for-deployed-environments) to create your infrastructure

### Terraform state credentials

The bootstrap module is used to create an s3 bucket for later terraform runs to store their state in. (If the bucket is already created, you should [Use bootstrap credentials](#use-bootstrap-credentials))

#### Bootstrapping the state storage s3 buckets for the first time

1. Within the `bootstrap` directory, run `terraform init`
1. Run `./run.sh plan` to verify that the changes are what you expect
1. Run `./run.sh apply` to set up the bucket
1. Follow instructions under [Use bootstrap credentials](#use-bootstrap-credentials)
1. Ensure that `import.sh` includes a line and correct IDs for any resources created
1. Run `./teardown_creds.sh` to remove the space deployer account used to create the s3 bucket
1. Copy `bucket` from `bucket_credentials` output to the backend block of `staging/providers.tf` and `production/providers.tf`

#### To make changes to the bootstrap module

*This should not be necessary in most cases*

1. Run `terraform init`
1. If you don't have terraform state locally:
    1. run `./import.sh`
    1. optionally run `./run.sh apply` to include the existing outputs in the state file
1. Make your changes
1. Continue from step 2 of the boostrapping instructions

## SpaceDeployers

A [SpaceDeployer](https://cloud.gov/docs/services/cloud-gov-service-account/) account is required to run terraform or
deploy the application from the CI/CD pipeline. Create a new account by running:

`./create_service_account.sh -s <SPACE_NAME> -u <ACCOUNT_NAME>`

## Workflow for deployed environments

These are the steps for developing Terraform code for our deployed environment modules (`sandbox`, `demo`, `staging` and `production`) locally on your laptop. Or for setting up a new deployment environment, or otherwise for running Terraform manually in any module that uses remote state. You don't need to do all this to run code in the `development` module, because it is not a deployed environment and it does not use remote state.

> [!CAUTION]
> There is one risky step below (`apply`) which is safe only in the `sandbox` environment and **should not** be run in any other deployed environment.

These steps assume shared [Terraform state credentials](#terraform-state-credentials) exist in s3, and that you are [Using those credentials](#use-bootstrap-credentials).

1. `cd` to the environment you plan to work in. When developing new features/resources, try out your code in `sandbox`. Only once the code is proven should you copy-and-paste it to each higher environment.

1. Run `cf spaces` and, from the output, copy the space name for the environment you are working in, such as `notify-sandbox`.

1. Next you will set up a SpaceDeployer. Prepare to fill in these values:
   * `<SPACE_NAME>` will be the string you copied from the prior step
   * `<ACCOUNT_NAME>` can be anything, although we recommend something that communicates the purpose of the deployer. For example: "circleci-deployer" for the credentials CircleCI uses to deploy the application, or "sandbox-<your_name>" for credentials to run terraform manually.

   Put those two values into this command:
    ```bash
    ./create_service_account.sh -s <SPACE_NAME> -u <ACCOUNT_NAME> > secrets.auto.tfvars
    ```

    The script will output the `username` (as `cf_user`) and `password` (as `cf_password`) for your `<ACCOUNT_NAME>`. The [cloud.gov service account documentation](https://cloud.gov/docs/services/cloud-gov-service-account/) has more information.

    The command uses the redirection operator (`>`) to write that output to the `secrets.auto.tfvars` file. Terraform will find the username and password there, and use them as input variables.

1. While still in an environment directory, initialize Terraform:
    ```bash
    terraform init
    ```

    If this command fails, you may need to run `terraform init -upgrade` to make sure new module versions are picked up. Or, `terraform init -migrate-state` to bump the remote backend.

1. Then, run Terraform in a non-destructive way:
    ```bash
    terraform plan
    ```

    This will show you any pending changes that Terraform is ready to make.

    :pencil: Now is the time to write any HCL code you are planning to write, re-running `terraform plan` to confirm that the code works as you develop. Keep in mind that any changes to the codebase that you commit will be run by the CI/CD pipeline.

1. **Only if it is safe to do so**, apply your changes.

    :skull: Applying changes in the wrong directory can mess up a deployed environment that people are relying on

    Double-check what directory you are in, like with the `pwd` command. You should probably only apply while in the `sandbox` directory / environment.

    Once you are sure it is safe, run:
    ```bash
    terraform apply
    ```

    This command *will deploy your changes* to the cloud. This is a healthy part of testing your code in the sandbox, or if you are creating a new environment (a new directory). **Do not** apply in environments that people are relying upon.

1. Remove the space deployer service instance when you are done manually running Terraform.
    ```bash
    # <SPACE_NAME> and <ACCOUNT_NAME> have the same values as used above.
    ./destroy_service_account.sh -s <SPACE_NAME> -u <ACCOUNT_NAME>
    ```

    Optionally, you can also `rm secrets.auto.tfvars`

## Structure

The `terraform` directory contains sub-directories (`staging`, `production`, etc.) named for deployment environments. Each of these is a *module*, which is just Terraform's word for a directory with some .tf files in it. Each module governs the infrastructure of the environment for which it is named. This directory structure forms "[bulkheads](https://blog.gruntwork.io/how-to-manage-terraform-state-28f5697e68fa)" which isolate Terraform commands to a single environment, limiting accidental damage.

The `development` module is rather different from the other environment modules. While the other environments can be used to create (or destroy) cloud resources, the development module mostly just sets up access to pre-existing resources needed for local software development.

The `bootstrap` directory is not an environment module. Instead, it sets up infrastructure needed to deploy Terraform in any of the environments. If you are new to the project, [this is where you should start](#retrieving-existing-bucket-credentials).

Similarly, `shared` is not an environment. It is a module that lends code to all the environments. Please note that changes to `shared` codebase will be applied to all envrionments the next time CI/CD (or a user) runs Terraform in that environment.

> [!WARNING]
> Editing `shared` code is risky because it will be applied to production

Files within these directories look like this:

```
- bootstrap/
  |- main.tf
  |- providers.tf
  |- variables.tf
  |- run.sh
  |- teardown_creds.sh
  |- import.sh
- <env>/
  |- main.tf
  |- providers.tf
  |- secrets.auto.tfvars
  |- variables.tf
```

In the environment-specific modules:
- `providers.tf` lists the required providers
- `main.tf` calls the shared Terraform code, but this is also a place where you can add any other services, resources, etc, which you would like to set up for that environment
- `variables.tf` lists the variables that will be needed, either to pass through to the child module or for use in this module
- `secrets.auto.tfvars` is a file which contains the information about the service-key and other secrets that should not be shared

In the bootstrap module:
- `providers.tf` lists the required providers
- `main.tf` sets up s3 bucket to be shared across all environments. It lives in `prod` to communicate that it should not be deleted
- `variables.tf` lists the variables that will be needed. Most values are hard-coded in this module
- `run.sh` Helper script to set up a space deployer and run terraform. The terraform action (`show`/`plan`/`apply`/`destroy`) is passed as an argument
- `teardown_creds.sh` Helper script to remove the space deployer setup as part of `run.sh`
- `import.sh` Helper script to create a new local state file in case terraform changes are needed

## Troubleshooting

### Expired token

```
The token expired, was revoked, or the token ID is incorrect. Please log back in to re-authenticate.
```
You need to re-authenticate with the Cloud Foundry CLI
```
cf login -a api.fr.cloud.gov --sso
```
You may also need to log in again to the Cloud.gov website.
