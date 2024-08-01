# Terraform

<img align="right" height="300" alt="illustration of space exploration" src="https://d2pn8kiwq2w21t.cloudfront.net/images/jpegPIA23900.width-1440.jpg">

This directory holds the Terraform modules for maintaining Notify.gov's API infrastructure. You might want to:
* [Set up](#retrieving-existing-bucket-credentials) the Sandbox and develop Terraform,
* [Maintain](#maintenance) software versions or CI/CD,
* [Learn](#structure) about the directory structure, or
* [Troubleshoot](#troubleshooting) error messages

The Admin app repo [has its own terraform directory](https://github.com/GSA/notifications-admin/tree/main/terraform) but a lot of the below instructions apply to both apps.

:tv: [Video introduction](https://drive.google.com/file/d/13SR3M8IowYBa4Wp_YEcuAURZ74EcCYoc/) to Notify infrastructure

## Retrieving existing bucket credentials

:green_book: New developers start here!

Assuming [initial setup](#initial-setup) is complete &mdash; which it should be if Notify.gov is online &mdash; Terraform state is stored in a shared remote backend. If you are going to be writing Terraform for any of our deployment environments you'll need to hook up to this backend. (You don't need to do this if you are just writing code for the `development` module, because it stores state locally on your laptop.)

1. Enter the bootstrap module with `cd bootstrap`
1. Run `./import.sh` to import the bucket containing remote terraform state into your local state
1. Follow instructions under [Use bootstrap credentials](#use-bootstrap-credentials)

### Use bootstrap credentials

1. Run `./run.sh show -json`.
1. In the output, locate `access_key_id` and `secret_access_key` within the `bucket_creds` resource. These values are secret, so don't share them with anyone or copy them to anywhere online.
1. Add the following to `~/.aws/credentials`:
    ```
    [notify-terraform-backend]
    aws_access_key_id = <access_key_id>
    aws_secret_access_key = <secret_access_key>
    ```
1. Check which AWS profile you are using with `aws configure list`. If needed, use `export AWS_PROFILE=notify-terraform-backend` to change to the profile and credentials you just added.

These credentials will allow Terraform to access the AWS/Cloud.gov bucket in which developers share Terraform state files. Now you are ready to develop Terraform using the [Workflow for deployed environments](#workflow-for-deployed-environments).

## Workflow for deployed environments

These are the steps for developing Terraform code for our deployed environment modules (`sandbox`, `demo`, `staging` and `production`) locally on your laptop. Or for setting up a new deployment environment, or otherwise for running Terraform manually in any module that uses remote state. You don't need to do all this to run code in the `development` module, because it is not a deployed environment and it does not use remote state.

> [!CAUTION]
> There is one risky step below (`apply`) which is safe only in the `sandbox` environment and **should not** be run in any other deployed environment.

These steps assume shared [Terraform state credentials](#terraform-state-credentials) exist in s3, and that you are [Using those credentials](#use-bootstrap-credentials).

1. `cd` to the environment you plan to work in. When developing new features/resources, try out your code in `sandbox`. Only once the code is proven should you copy-and-paste it to each higher environment.

1. Run `cf spaces` and, from the output, copy the space name for the environment you are working in, such as `notify-sandbox`.

1. Next you will set up a SpaceDeployer service account instance. This is something like a stub user account, just for deployment. Note these two values which you will use both to create and destroy the account:
    1. `<SPACE_NAME>` will be the string you copied from the prior step
    1. `<ACCOUNT_NAME>` can be anything, although we recommend something that communicates the purpose of the deployer. For example: "circleci-deployer" for the credentials CircleCI uses to deploy the application, or "sandbox-<your_name>" for credentials to run terraform manually.

    Put those two values into this command:
    ```bash
    ../create_service_account.sh -s <SPACE_NAME> -u <ACCOUNT_NAME> > secrets.auto.tfvars
    ```

    The script will output the `username` (as `cf_user`) and `password` (as `cf_password`) for your `<ACCOUNT_NAME>`. The [cloud.gov service account documentation](https://cloud.gov/docs/services/cloud-gov-service-account/) has more information.

    Some resources you might work on require a SpaceDeployer account with higher permissions. Add the `-m` flag to the command to get this.

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

    :pencil: Now is the time to write any HCL code (aka Terraform code) you are planning to write, re-running `terraform plan` to confirm that the code works as you develop. Keep in mind that any changes to the codebase that you commit will be run by the CI/CD pipeline.

1. **Only if it is safe to do so**, apply your changes.

    :skull: Applying changes in the wrong directory can mess up a deployed environment that people are relying on

    Double-check what directory you are in, like with the `pwd` command. You should probably only apply while in the `sandbox` directory / environment.

    Once you are sure it is safe, run:
    ```bash
    terraform apply
    ```

    This command *will deploy your changes* to the cloud. This is a healthy part of testing your code in the sandbox, or if you are creating a new environment (a new directory). **Do not** apply in environments that people are relying upon.

    If you need to go on to deploy application code on top of the resources you just instantiated, you will [use `cf push`](https://github.com/GSA/notifications-api/blob/main/docs/all.md#deploying-to-the-sandbox)

1. Remove the space deployer service instance when you are done manually running Terraform.
    ```bash
    # <SPACE_NAME> and <ACCOUNT_NAME> have the same values as used above.
    ./destroy_service_account.sh -s <SPACE_NAME> -u <ACCOUNT_NAME>
    ```

    List `cf services` if you are unsure which space deployer service instances still exist

    Optionally, you can also `rm secrets.auto.tfvars`

## Maintenance

### Version upgrade checklist

* Cloud Foundry Terraform plugin in every module in the API and Admin apps, [here for example](sandbox/providers.tf#L6).
* The [terraform-cloudgov module](https://github.com/GSA-TTS/terraform-cloudgov/), the version of which is referred to serveral times in most modules, [here for example](sandbox/main.tf#16).
* Cloud Service Broker (CSB) version in [the SMS](https://github.com/GSA/usnotify-ssb/blob/main/app-setup-sms.sh) and [the SMTP](https://github.com/GSA/usnotify-ssb/blob/main/app-setup-smtp.sh) download scripts of the usnotify-ssb repo.
* SMS and SMTP brokerpak versions, also in the download scripts of the usnotify-ssb repo, along with with the [SMTP brokerpak project](https://github.com/GSA-TTS/datagov-brokerpak-smtp) itself.
* The version of Redis used in deployed environment modules, [here for example](sandbox/main.tf#33). To upgrade, the resource must be destroyed and replaced. The versions supported are limited by Cloud.gov.


### SpaceDeployers

A [SpaceDeployer](https://cloud.gov/docs/services/cloud-gov-service-account/) account is required to run terraform or
deploy the application from the CI/CD pipeline. During CI/CD maintenance you might need to create a new account:

`./create_service_account.sh -s <SPACE_NAME> -u <ACCOUNT_NAME>`

SpaceDeployers are also needed to run Terraform locally &mdash; they fill user and password input variables (via `deployers` within `main.tf`) that some of our Terraform modules require when they start running. Using a SpaceDeployer account locally is covered in [Workflow for deployed environments](#workflow-for-deployed-environments).

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

### CF account not authorized

```
Error: You are not authorized to perform the requested action
```
This error indicates that the Cloud Foundry user account (or service account) needs OrgManager permissions to take the action.
* When you create a SpaceDeployer service account, use the `-m` flag when running the `./create_service_account.sh` script
* Your own CF user may may also require OrgManager permissions to run the script

### Services limit
```
You have exceeded your organization's services limit.
```
Too many Cloud Foundry services have been created without being destroyed. Perhaps Terraform developers have forgotten to delete their SpaceDeployers after they finish with them. List `cf services` to see.

### Unknown error
```
Error: Service Instance xx-name-xx failed xx-UUID-xx, reason: [Job (xx-UUID-xx) failed: An unknown error occurred.]
```
This unhelpful message may be clarified by looking in the Cloud.gov web UI. Among the list of service instances (Cloud Foundry &#x2192; Organizations &#x2192; gsa-tts-benefits-studio &#x2192; Spaces &#x2192; your-space-name &#x2192; Service instances) check for pending or erroring items. Refer below if you discover a [domain identity verification](#Domain_identity_verification) error.

The audit event logs may also provide insight. They are visible in web UI or [in the terminal](https://v3-apidocs.cloudfoundry.org/version/3.159.0/#audit-events).

### Domain identity verification
```
Error: Error creating SES domain identity verification: Expected domain verification Success, but was in state Pending
```
This error comes via the [Supplementary Service Broker](https://github.com/GSA/usnotify-ssb/) and originates from the [SMTP Brokerpak](https://github.com/GSA-TTS/datagov-brokerpak-smtp) it uses. You can run the [broker provisioning locally](https://github.com/GSA-TTS/datagov-brokerpak-smtp/tree/main/terraform/provision) to tinker with the error.

### Validating provider credentials
```
Error: validating provider credentials: retrieving caller identity from STS: operation error STS: GetCallerIdentity, https response error StatusCode: 403
```
The steps in [Use bootstrap credentials](#use-bootstrap-credentials) may not be complete. Or the AWS CLI may have reverted to the default profile, in which case, re-run:
```bash
export AWS_PROFILE=notify-terraform-backend
```

### No valid credential sources
```
Error: No valid credential sources found
Please see https://www.terraform.io/docs/language/settings/backends/s3.html for more information about providing credentials.

Error: failed to refresh cached credentials, no EC2 IMDS role found, operation error ec2imds: GetMetadata, request canceled, context deadline exceeded
```
You are not hooked up to the remote backend that stores Terraform state
Run steps in [Retrieving existing bucket credentials](#retrieving-existing-bucket-credentials).

### Space Deployers will be updated in-place
```
# module.egress-space.cloudfoundry_space_users.deployers will be updated in-place
  ~ resource "cloudfoundry_space_users" "deployers" {
      ~ developers = [
          - "xxx-GUID-xxx",
          + "yyy-GUID-yyy",
```
The environment was last deployed by someone other than you, using a different Space Deployer account. If you are working in the Sandbox environment, this is fine; go ahead and apply the changes. After you do, the other person evidently also working in the Sandbox env will then see the same message. The two of you might play tug-of-war with different GUIDs, but this is inconsequential.
