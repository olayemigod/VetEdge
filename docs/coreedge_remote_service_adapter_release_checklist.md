# VetEdge Remote CoreEdge Adapter — Release Gate

This checklist is the merge and rollout gate for the VetEdge V3.0B reference adapter.

## Automated verification

- `python -m compileall -q vetedge`
- Ruff passes for `vetedge/platform_client.py`, `vetedge/services/platform_access.py`, and `vetedge/tests/test_remote_platform_client.py`.
- `vetedge.tests.test_remote_platform_client` passes.
- `vetedge.services.test_platform_access` passes.
- `vetedge.tests.test_coreedge_adapter` passes.
- Scheduled heartbeat failures remain visible even while an unexpired allowed access decision is cached.
- The existing VetEdge Frappe v16 integration suite remains green without CoreEdge installed locally.

## Authority governance

- Remote credentials alone do not activate remote authority.
- `coreedge_authority_mode = remote` performs the controlled cutover.
- `coreedge_remote_required = 1` is a non-bypassable operator policy and overrides `legacy_auto`.
- No Veterinary Settings field or tenant-facing switch may change platform authority.

## Central dependency

- CoreEdge V3.0A Service Gateway is migrated on the selected central CoreEdge site.
- A dedicated non-privileged integration user exists.
- A `CoreEdge Service Client` binds that user to the correct tenant, VetEdge product, and exact site identifier.
- The corresponding tenant and VetEdge activation are active.

## Reference-site rollout

1. Explicitly keep the site on `coreedge_authority_mode = legacy_auto` while provisioning and testing credentials.
2. Add the central URL, API key, API secret, site identifier, and VetEdge product name through protected site configuration.
3. Test the remote handshake and configuration before selecting `coreedge_authority_mode = remote`.
4. Confirm an allowed decision permits protected VetEdge operations.
5. Confirm tenant or activation suspension blocks protected operations.
6. Confirm an outage uses only an unexpired allowed cache decision and fails closed after expiry.
7. Confirm the scheduled heartbeat reports an outage instead of masking it with the access-decision cache.
8. Confirm local CoreEdge controls are absent from VetEdge boot data in remote mode.
9. Set `coreedge_remote_required = 1` after the reference rollout is accepted and fallback must no longer be permitted.
10. Remove local CoreEdge from the reference site only after the complete end-to-end checklist passes.

## Rollback

Rollback is an operator action. Restore `coreedge_authority_mode = legacy_auto` only during the controlled migration period, before `coreedge_remote_required = 1` becomes mandatory, and only after confirming the local CoreEdge data is current and authoritative. Do not silently fall back from remote authority during normal operation.
