# ADR: Handle paid quotas at the organization level

Status: Accepted
Date: September 30, 2023

### Context

Currently, each service has a separate maximum limit for annual messages. Because we expect that (1) partners will want more than one service and (2) limits will vary from partner to partner based on their budget, setting limits at the service level is more difficult than a organization-level quota.

We have already decided to [connect organizations and agreements together](.docs/adrs/0005-agreement-data-model.md).

### Decision

We will move paid and free quotas from `Service` to `Organization`. Each service should draw its quota from its associated organization.

Any conversion between dollars and messages should happen upstream of these models, in the `Agreement` class.

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

**Step 1: Data flow**
- Add a method that determines the active `Agreement` for an `Organization` based on the agreement's period of performance and signed status
- Add a method that determines a quota for `Organization` based on the linked `Agreement` value
- Move existing `Service` quota to exist on the organization instead
- Add method for service to determine its remaining quota based on the organization

**Step 2: Usage calculations**
- Add a method to calculate message usage for an organization
- Update sending validator to use the organization limit

**Step 3: Cleanup**
- Remove service `organization_type`
- Add local, tribal, and territory to `ORGANIZATION_TYPES`
- Remove legacy `agreement_*` fields from `Organization`

**Step 4: Follow-up ADRs**
- ADR for IAA support with paid message quotas
- ADR for usage calculation (i.e. Redis key vs DB counting)
