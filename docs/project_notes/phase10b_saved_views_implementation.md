# Phase 10B — Private Named Report Views

Status: **Implementation complete; automated/browser QA pending.**

## Goal

Provide private user-owned saved report views without introducing a new VetEdge DocType, shared-view permission model, or product-specific report shell.

## Storage

VetEdge uses Frappe v16's existing per-user `__UserSettings` mechanism through `frappe.model.utils.user_settings`.

- scope: `VetEdge Report Center`;
- key: `vetedge_report_views_v1`;
- maximum 25 private views per user;
- no new schema migration;
- Frappe synchronizes cached user settings to the database through its hourly-maintenance `sync_user_settings` job.

## Stored state

Only normalized report-view metadata is stored:

- view id;
- private view name;
- report name/key;
- allowlisted filters;
- visible column keys;
- internal ordering/default marker;
- created/modified timestamps.

Report rows, chart datasets, summary values, invoices, clinical records, or other result data are never stored in a saved view.

## Security and privacy

- Guest is blocked.
- All list/save/rename/apply operations are current-user only.
- Report View authorization is revalidated on list/save/rename/apply.
- Advanced-report entitlement is therefore revalidated as part of report View authorization.
- Saved-view list returns metadata only; stored Patient/Owner/filter state is not returned in the list response.
- Applying a view explicitly revalidates the stored state against current Branch/report context.
- A stale Branch assignment is removed and current server Branch normalization is reapplied.
- Smart-filter values such as Patient, Owner, Practitioner, Consultation Type, Item, Vaccine, Species and Breed are rechecked against the existing bounded permission-aware report filter search where that report supports them.
- Invalid/stale filters are removed without returning their old value to the client; the response returns only the removed filter keys so the UI can warn the user.
- Deleting a view remains current-user-only and does not disclose stored state.

## Report Center UX

Report Center provides:

- Saved Views dropdown;
- Save View;
- Rename;
- Delete.

Applying a view:

1. calls the explicit state-validation endpoint;
2. replaces the current allowlisted filters and visible-column state;
3. updates the shareable URL;
4. resets pagination to page 1;
5. performs exactly one normal provider refresh.

Manual filter or column changes clear the selected-view marker so the UI never claims an edited state still matches the saved definition.

The UI does not auto-apply a default saved view in this slice. This avoids an extra initial report load. Default-view startup behavior should only be introduced with a single-load initialization design.

## Performance

- Saved-view list is small metadata only.
- No report result rows are persisted or loaded for saved-view management.
- Saved-view state validation happens only when a user explicitly applies a view.
- Applying a view performs one state-validation request and one normal report-provider refresh.
- Column-only edits remain presentation-only and do not reload the provider.

## Explicitly out of scope

- team/shared/public saved views;
- role-owned views;
- Branch-owned views;
- administrative publishing;
- cross-product/CoreEdge saved-view management;
- default-view auto-application;
- scheduled delivery.

Those require explicit tenant, ownership, publishing, audit and reauthorization rules.

## Source contracts

- `vetedge/tests/test_report_saved_views_contract.py`
- `vetedge/tests/test_report_center_saved_views_ui_contract.py`
- `vetedge/tests/test_report_center_view_state_contract.py`

These are implementation guards only. Browser and full automated acceptance remain required before merge.
