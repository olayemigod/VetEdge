# VetEdge → CoreEdge V2.4E Context Inventory Sync

## Goal

Submit VetEdge's full normalized operating-unit inventory to the CoreEdge V2.4D authenticated inventory service without making CoreEdge an installed-app dependency.

## Local authority

VetEdge remains authoritative for its local workflow, permissions and accounting-safe context rules.

The sync uses the existing read-only normalizer:

`vetedge.services.coreedge_context_reconciliation.get_context_reconciliation_rows`

and sends only the common reconciliation fields. Product-specific diagnostic fields are not transmitted.

## Private site configuration

Configure these values in the product site's private site configuration:

- `coreedge_service_url`;
- `coreedge_service_site_identifier`;
- `coreedge_service_api_key`;
- `coreedge_service_api_secret`.

Optional:

- `coreedge_service_timeout_seconds` — bounded to 3–60 seconds, default 15;
- `coreedge_service_allow_insecure_http = 1` — controlled local QA only.

HTTPS is required by default.

The API token must belong to the dedicated CoreEdge Service Client integration user registered for this exact product site. CoreEdge must grant that Service Client:

- feature `context_governance`;
- action `submit_inventory`.

## Operator action

`vetedge.services.coreedge_context_sync.submit_context_inventory_to_coreedge()`

is restricted to Administrator/System Manager.

The function:

1. builds the product's full normalized inventory;
2. strips non-contract metadata;
3. derives an hourly idempotency key from the normalized payload unless one is supplied;
4. calls CoreEdge V2.4D using token authentication;
5. returns the bounded CoreEdge acknowledgement.

Repeated submission of the unchanged payload in the same hour reuses the same default idempotency key. A changed payload receives a different key.

## Safety

The sync does not:

- import the CoreEdge Python package;
- mutate local Branch/Campus records;
- change local user permissions;
- create local platform mappings;
- change Company, Cost Center, Warehouse, POS, pricing or accounting defaults;
- mutate submitted ERPNext accounting documents;
- switch active runtime context;
- log the configured API secret.

## Rollout

Do not schedule automatic submissions yet. First validate manual submission against a non-production CoreEdge Service Client and confirm the resulting immutable CoreEdge inventory snapshot. Automated periodic sync can be added only after the operator reconciliation workflow is accepted.
