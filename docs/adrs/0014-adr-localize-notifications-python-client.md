# Bring in the notifications-python-client directly to the API and Admin apps

Status: Accepted
Date: 10 June 2025

### Context

We still pull in the `notifications-python-client` as a third party library, and it is what underpins all of the requests made throughout the API and admin applications.  Our apps have diverged enough from the original UK Notify applications that we ought to consider making our own copy of this library for our apps to make sure the client continues to meet our use cases and we aren't suddenly caught in a bind with an update that won't work for us.

Furthermore, we need to make some adjustments to this library in order to continue updating Python (e.g. Python 3.13) due to some incompatibilities, such as how SSL certificates are validated.

### Decision

We're going to pull in the `notifications-python-client` library (source code found here: https://github.com/alphagov/notifications-python-client to both the API and Admin apps just like we did with the `notifications-utils` library/repo.  This will involve doing the following:

* Making a local copy of the `https://github.com/alphagov/notifications-python-client` code base (the code for the library itself - likely just what's in https://github.com/alphagov/notifications-python-client/tree/main/notifications_python_client but we need to double check) within a `notifications_python_client` folder at the root of the project directory.
* Incorporating any of the dependencies required for the library into our own directly (in the `pyproject.toml` file) that aren't already accounted for.
* Making sure all namespaces (e.g., `import` statements) within our app for references to the library continue to work still.
* Make sure tests are included/excluded as appropriate (similar to what we did with `notifications_utils`).

### Consequences

We anticipate the impacts to our project and team to be the following:

* No longer gaining any updates the library directly that are published to PyPI.
* Slight increased burden in codebase maintenance.
* A bit of extra work to incorporate the library in fully and completely to the API and Admin directly.
* No longer sharing code between the API and Admin; any changes made to the `notifications-python-client` in one app will need to be mirrored in the other.

However, we also anticipate these benefits in doing this work:

* Gaining full control of future changes to the `notifications-python-client` code.
* Ability to reduce the `notifications-python-client`'s footprint for our own needs and use cases.
* Ability to make changes and updates necessary to keep the other parts of the application up-to-date (e.g., Python updates)
* Removing reliance on a third-party dependency that we have no control over.

### Author

@ccostino

### Stakeholders

@ccostino

### Next Steps

Next steps once this draft ADR is posted:

* Team reviews the ADR and makes adjustments as necessary
* Team agrees on the approach of the ADR and finalizes it for acceptance (creates a proper ADR file for it)
* Issue(s) get created to perform the work in the API and the Admin
