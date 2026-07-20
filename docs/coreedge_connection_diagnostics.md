# VetEdge V3.0C — CoreEdge Connection Diagnostics

## Goal

Allow authorised VetEdge operators to verify the remote CoreEdge configuration and perform a fresh authenticated handshake before changing platform authority or removing a local CoreEdge installation.

The diagnostic is intentionally non-destructive:

- it does not write site configuration;
- it does not switch `coreedge_authority_mode`;
- it does not enable `coreedge_remote_required`;
- it does not uninstall or disable local CoreEdge;
- it does not expose the API key or API secret;
- it does not use a cached decision when the live check fails.

## Authorised Roles

- System Manager
- VetEdge Administrator

Normal doctors, nurses, front-desk users, cashiers, portal users, and other operational roles cannot run the diagnostic.

## Static Diagnostic

Method:

```text
vetedge.services.platform_diagnostics.get_remote_platform_diagnostic
```

The static diagnostic performs no external HTTP request. It reports:

- current operator-controlled authority mode;
- whether remote authority is mandatory;
- whether remote mode is currently requested;
- CoreEdge service host, without credentials or URL query data;
- site identifier;
- product app identity;
- configured timeout;
- missing or invalid configuration keys;
- current secret-free cache status;
- confirmation that no authority or local-app change was performed.

## Live Diagnostic

POST method:

```text
vetedge.services.platform_diagnostics.run_remote_platform_diagnostic
```

The live diagnostic:

1. validates the protected site configuration;
2. forces a fresh V1 handshake;
3. disables allowed-cache fallback for the diagnostic request;
4. relies on the product client to validate API version, service identity, site binding, product binding, tenant consistency, and the fail-closed contract;
5. returns a secret-free summary of the registered client, access decision, cache policy, heartbeat interval, and response duration.

Possible status values include:

- `Ready` — authenticated and currently allowed;
- `Blocked` — authenticated and correctly bound, but CoreEdge currently blocks access;
- `Misconfigured` — required protected configuration is missing or invalid;
- `Authentication Failed` — the token was rejected;
- `Unavailable` — the service could not be reached or returned an HTTP failure;
- `Contract Error` — the response failed the expected gateway contract;
- `Failed` — another controlled remote-platform error occurred.

A `Blocked` result is not a connectivity failure. It proves the site authenticated successfully but the tenant, product activation, trial, grace, or other central access condition currently prevents operation.

## Pre-Cutover Procedure

1. Keep `coreedge_authority_mode = legacy_auto` during provisioning.
2. Add the central service URL, API key, API secret, exact site identifier, and `VetEdge` product identity through protected site configuration.
3. Run the static diagnostic and resolve every missing or invalid setting.
4. Run the live diagnostic and require `Ready` for the approved reference tenant.
5. Suspend the central tenant or activation and confirm the diagnostic returns `Blocked` with the expected reason code.
6. Restore central access and confirm `Ready` returns on a fresh diagnostic.
7. Test an intentional service outage and confirm `Unavailable`; the diagnostic must not hide the outage with the access cache.
8. Only after acceptance, set `coreedge_authority_mode = remote`.
9. Set `coreedge_remote_required = 1` when rollback to local authority must no longer be permitted.
10. Remove local CoreEdge from the reference site only after the complete rollout checklist passes.

## Tests

```bash
bench --site vetedge.local run-tests \
  --app vetedge \
  --module vetedge.tests.test_platform_diagnostics
```

Coverage includes secret redaction, static checks, forced fresh handshake, blocked decisions, authentication failure classification, incomplete configuration, operator permissions, unchanged authority settings, and filtering of unexpected secret fields.

## Out of Scope

- automatic site-config writes;
- automatic authority cutover;
- automatic CoreEdge uninstall;
- remote tenant or activation changes;
- credential rotation or revocation from VetEdge;
- notification, payment, wallet, or EdgeFinder service diagnostics.
