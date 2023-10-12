# ADR: Handle paid quotas at the organization level

Status: Accepted
Date: September 30, 2023

### Context

Currently, each service has a separate maximum limit for annual messages. Because we expect that (1) partners will want more than one service and (2) limits will vary from partner to partner based on their budget, setting limits at the service level is more difficult than a organization-level quota.

We have already decided to [connect organizations and agreements together](.docs/adrs/0005-agreement-data-model.md).

### Decision

We will move paid and free quotas from `Service` to `Organization`. Each service should draw its quota from its associated organization.

We considered moving paid quotas while leaving free quotas at the service level, but as our current MOU specifies the total messages that would create some service-management headaches.

We also considered validating service quotas based on organization-associated agreements. This would add some configurability, but is over-complex for the application's current usage.

### Consequences

In order to move out of trial mode, services will need to be linked to an organization. This should already be included as part of the "go live" process, but might be able to move earlier in the process. An admin might want to link an organization at or shortly after service creation.

At this time, services will pull directly from the organization's quota. We may find that there's a need for subquotas down the road, which might add a similar validation setup that we considered here.

### Author

@stvnrlly, @ccostino, @tdlowden 

### Stakeholders

@amyashida 

### Next Steps

- Add a method that determines a quota for `Organization` based on the linked `Agreement` value
- Move existing `Service` quota to exist on the organization instead
- Add method for service to determine its remaining quota based on the organization
- Add a method to calculate message usage for an organization
- Add organization selection to service creation form
- Add sending validator for the organization limit
- Convert service `organization_type` to pull from associated organization instead of being a separate field
- Add a sandbox organization for unaffiliated trial-only services