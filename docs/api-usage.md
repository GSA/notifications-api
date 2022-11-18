# API Usage

## Connecting to the API

To make life easier, the [UK API client libraries](https://www.notifications.service.gov.uk/documentation) are compatible with Notify.

For a usage example, see [our Python demo](https://github.com/GSA/notify-python-demo).

An API key can be created at https://notifications-admin.app.cloud.gov/services/YOUR_SERVICE_ID/api/keys. However, in order to successfully send messages, you will need to receive a secret header token from the Notify team.


## Using OpenAPI documentation

### Retrieving a jwt-encoded bearer token for use

On a mac, run

#### Admin UI token

```
flask command create-admin-jwt | tail -n 1 | pbcopy
```

#### User token

```
flask command create-user-jwt --token=<USER_API_TOKEN> | tail -n 1 | pbcopy
```

to copy a token usable by the admin UI to your pasteboard. This token will expire in 30 seconds

### Disable token expiration checking in development

Because jwt tokens expire so quickly, the development server can be set to allow tokens older than 30 seconds:

```
env ALLOW_EXPIRED_API_TOKEN=1 make run-flask
```
