# API Usage

## Connecting to the API

To make life easier, the [UK API client libraries](https://www.notifications.service.gov.uk/documentation) are compatible with Notify and the [UK API Documentation](https://docs.notifications.service.gov.uk/rest-api.html) is applicable.

For a usage example, see [our Python demo](https://github.com/GSA/notify-python-demo).

An API key can be created at https://HOSTNAME/services/YOUR_SERVICE_ID/api/keys. This is the same API key that is referenced as `USER_API_TOKEN` below.

## Postman Documentation

Internal-only  [documentation for exploring the API using Postman](https://docs.google.com/document/d/1S5c-LxuQLhAtZQKKsECmsllVGmBe34Z195sbRVEzUgw/edit#heading=h.134fqdup8d3m)


## Using OpenAPI documentation

An [OpenAPI](https://www.openapis.org/) specification [file](./openapi.yml) can be found at https://notify-staging.app.cloud.gov/docs/openapi.yml.

See [writing-public-apis.md](./writing-public-apis.md) for links to tools to make it easier to use the OpenAPI spec within VSCode.

### Retrieving a jwt-encoded bearer token for use

On a mac, run:

#### Admin UI token

The admin UI token is required for any of the `internal-api` tagged methods. To create one and copy it to your pasteboard, run:

```
flask command create-admin-jwt | tail -n 1 | pbcopy
```

#### User token

A user token is required for any of the `external-api` tagged methods. To create one and copy it to your pasteboard, run:

```
flask command create-user-jwt --token=<USER_API_TOKEN> | tail -n 1 | pbcopy
```

### Disable token expiration checking in development

Because jwt tokens expire so quickly, the development server can be set to allow tokens older than 30 seconds:

```
env ALLOW_EXPIRED_API_TOKEN=1 make run-flask
```
