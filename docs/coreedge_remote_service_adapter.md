# VetEdge Platform V3.0B — Remote CoreEdge Access Adapter

## Business Goal

Allow VetEdge to operate as a product app that depends on a centrally managed CoreEdge service without requiring the `coreedge` app to be installed on the VetEdge site.

This phase uses VetEdge as the reference product integration for the CoreEdge V3.0A Service Gateway.

The operating rule is:

- CoreEdge owns tenant and product activation authority.
- VetEdge asks CoreEdge for a machine-to-machine access decision.
- The VetEdge site cannot submit an arbitrary tenant or product to CoreEdge.
- Remote authority fails closed when no valid decision is available.
- Remote authority never falls back to a locally installed CoreEdge app.
- Credentials remain in protected operator configuration, not DocTypes or browser assets.

## Scope Delivered

### 1. Remote CoreEdge client

`vetedge.platform_client` provides:

- Frappe token-authenticated calls to the CoreEdge V1 Service Gateway;
- lazy handshake on the first protected action;
- scheduled heartbeat every five minutes;
- runtime access checks before VetEdge protected mutating actions;
- server-authoritative decision caching;
- fail-closed handling after cache expiry;
- strict response validation for API version, service identity, site binding, product binding, tenant consistency, and cache policy;
- secret-free boot status;
- controlled errors for configuration, authentication, availability, protocol, and access denial failures.

### 2. Existing VetEdge workflow gates

The existing `vetedge.services.platform_access.require_vetedge_platform_access` wrapper now resolves the operator-selected authority:

- `remote`: use the central CoreEdge Service Gateway;
- `legacy_auto`: retain the existing local adapter during controlled migration.

All currently gated VetEdge mutating workflows continue using the same wrapper, including appointments, consultations, billing, lab, vaccination, hospitalisation, grooming, and boarding.

No business-service module imports CoreEdge directly.

### 3. No remote-to-local fallback

Once `coreedge_authority_mode` is set to `remote`, failures do not fall back to locally installed CoreEdge data.

This protects against a dangerous scenario where:

1. CoreEdge centrally suspends a tenant or product;
2. the product site cannot reach CoreEdge;
3. the product site bypasses the suspension by consulting an old local copy.

A still-valid cached **allowed** decision may be used only until its CoreEdge-provided TTL expires. After expiry, the action is blocked until CoreEdge can be reached again.

### 4. Cache contract

VetEdge honours the cache policy returned by CoreEdge:

- allowed-decision TTL;
- blocked-decision TTL;
- `fail_closed: true`.

VetEdge independently caps any allowed TTL at five minutes. It does not create an unlimited local grace period.

### 5. Network safety

The client:

- requires HTTPS by default;
- permits HTTP only when both `developer_mode` and `coreedge_allow_insecure_http` are enabled;
- disables HTTP redirects so the Authorization header cannot be forwarded to another host;
- uses a bounded request timeout of 1–30 seconds;
- does not log request headers, API keys, API secrets, or response credentials;
- validates that CoreEdge returns the registered VetEdge site and product binding.

## Site Configuration

Configure these keys in the VetEdge site's protected `site_config.json`, environment-backed site configuration, or Frappe Cloud secret configuration.

```json
{
  "coreedge_authority_mode": "remote",
  "coreedge_service_url": "https://platform.edgesuite.africa",
  "coreedge_api_key": "<dedicated-service-user-api-key>",
  "coreedge_api_secret": "<dedicated-service-user-api-secret>",
  "coreedge_site_identifier": "portal.example.com",
  "coreedge_remote_timeout_seconds": 5,
  "edge_platform_product": "VetEdge"
}
```

Do not place the API secret in:

- Veterinary Settings;
- any custom DocType;
- Client Script;
- browser JavaScript;
- source control;
- logs;
- support screenshots.

### Local development over HTTP

Only a developer site may use an HTTP CoreEdge URL:

```json
{
  "developer_mode": 1,
  "coreedge_allow_insecure_http": 1,
  "coreedge_service_url": "http://coreedge.local:8000"
}
```

Never enable this override in production.

## CoreEdge Provisioning Prerequisites

Before switching a VetEdge site to remote authority:

1. Merge and migrate CoreEdge V3.0A on the central CoreEdge site.
2. Confirm the tenant exists and is active.
3. Confirm the VetEdge product registry record is active.
4. Confirm the tenant has an active or valid trial/grace VetEdge activation.
5. Create a dedicated Frappe System User on CoreEdge.
6. Assign the dedicated user only the `CoreEdge Service Client` role and unavoidable baseline roles.
7. Generate that user's API key and API secret.
8. Create a `CoreEdge Service Client` record bound to:
   - the correct tenant;
   - `VetEdge`;
   - the exact VetEdge site identifier;
   - the dedicated integration user.
9. Test the CoreEdge handshake directly.
10. Add the protected connection settings to the VetEdge site.
11. Clear cache and restart workers.
12. Test VetEdge remote access before removing local CoreEdge.

Use one CoreEdge integration user and service-client registration per product site. Do not reuse a privileged administrator account across tenants or sites.

## Safe Rollout Sequence

### Phase A — Deploy without changing authority

Deploy the VetEdge adapter while leaving sites on `legacy_auto`.

Existing behaviour remains unchanged. This is the backward-compatible migration state.

### Phase B — Provision one reference site

Provision one non-production or controlled VetEdge site in central CoreEdge and add its credentials.

Set:

```json
"coreedge_authority_mode": "remote"
```

Run the handshake and protected-action tests.

### Phase C — Dual-install verification

It is acceptable for CoreEdge to remain locally installed briefly while verifying remote mode, but remote mode will not use it as a fallback and local CoreEdge controls are hidden.

### Phase D — Remove local CoreEdge dependency

After remote verification:

1. take a backup;
2. confirm no VetEdge code imports local CoreEdge outside the legacy adapter;
3. remove CoreEdge from the product site using the approved Frappe app-removal process;
4. migrate and rebuild;
5. repeat access, suspension, billing, and clinical workflow QA.

### Phase E — Wider rollout

Repeat central provisioning and remote activation site by site. Do not bulk-switch unprovisioned tenants.

A later governance phase may change the default authority from `legacy_auto` to `remote` after all active product sites have central service-client registrations.

## User-Facing Behaviour

Normal VetEdge users see neutral operational messages:

- Platform Access Required;
- Platform Connection Required;
- Platform access could not be verified.

They do not see API keys, secrets, service-client internals, or tenant administration controls.

Remote mode also hides local CoreEdge workspace and platform-control links from VetEdge boot information.

## Automated Tests

Run:

```bash
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_remote_platform_client

bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.services.test_platform_access

bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_coreedge_adapter
```

Then run the full VetEdge suite:

```bash
bench --site vetedge.local run-tests --app vetedge
```

The focused remote-client tests cover:

- migration-safe authority selection;
- fail-safe handling of unsupported authority values;
- HTTPS enforcement and developer HTTP override;
- token-authenticated handshake;
- omission of tenant and product parameters from client requests;
- redirect rejection;
- request timeout/network failure;
- valid cache reuse;
- bounded stale-cache fallback during forced refresh;
- site and product response-binding validation;
- blocked decisions;
- five-minute maximum TTL;
- secret-free status output;
- local CoreEdge UI hiding in remote mode;
- protected workflow routing without local fallback;
- incomplete configuration blocking;
- scheduler no-op in legacy mode.

## Manual QA Checklist

### Central CoreEdge

- Confirm CoreEdge V3.0A is migrated.
- Confirm the service user is non-privileged.
- Confirm the service-client site identifier exactly matches VetEdge.
- Confirm the tenant and VetEdge activation are active.
- Confirm the direct handshake succeeds.

### VetEdge

- Confirm the site starts normally in `legacy_auto` before activation.
- Add the remote configuration and restart workers.
- Clear cache.
- Log in and confirm no API secret appears in boot data.
- Confirm local CoreEdge controls are hidden.
- Perform a protected appointment or consultation action and confirm it succeeds.
- Confirm CoreEdge records the heartbeat and version.
- Repeat the action within the allowed TTL and confirm it uses cache.
- Suspend the tenant centrally and wait for or force a fresh check.
- Confirm protected actions are blocked.
- Restore the tenant and confirm access returns after a fresh decision.
- Change the CoreEdge service-client site identifier and confirm VetEdge rejects the response/call.
- Revoke the service client and confirm VetEdge fails closed.
- Stop the central CoreEdge service and confirm:
  - a still-valid cached allowed decision works only until expiry;
  - actions fail closed after expiry.
- Confirm reports and read-only screens remain available only where intentionally ungated.
- Run billing, payment, stock, lab, vaccination, grooming, boarding, and hospitalisation regression QA.

## Backward Compatibility

- Existing `legacy_auto` behaviour remains available for migration.
- Existing local CoreEdge adapter functions are not deleted.
- Existing protected service entry points are not rewritten.
- Existing accounting and clinical logic is unchanged.
- No submitted ERPNext accounting document is mutated.
- No database field is added for connection credentials or authority selection.

## Out of Scope

This phase does not implement:

- remote SMS, email, WhatsApp, wallet, payment, or EdgeFinder APIs;
- end-user identity federation;
- central branch/company context for remote users;
- OAuth2, mutual TLS, or request signing;
- automatic CoreEdge app removal;
- a tenant-facing switch to disable platform authority;
- bulk rollout to all VetEdge sites;
- RetailEdge, EduEdge, or other product adapters.

## Next Recommended Phase

**CoreEdge/VetEdge V3.0C — Reference-Site Provisioning and Live End-to-End Verification** should:

1. migrate the central CoreEdge V3.0A branch;
2. provision a VetEdge service client;
3. configure one reference VetEdge site;
4. run live handshake, cache, suspension, recovery, and worker-heartbeat tests;
5. remove local CoreEdge from that reference site only after successful verification;
6. produce the reusable rollout checklist for RetailEdge and other EdgeSuite products.
