# Hospitalisation EdgeSuite Operational Audit

## Goal

Complete Hospitalisation as a clean EdgeSuite operational workflow without rebuilding clinical, billing or stock logic that already exists.

## Current implementation status

### Already implemented and should be preserved

Hospitalisation is not a skeletal feature. The existing implementation already provides:

- Veterinary Settings enable/disable control;
- configurable Full / Partial / No Payment Gate;
- configurable consultation/direct-admission and initial-billing source behavior;
- patient/owner/Branch/company/attending-veterinarian context;
- Admit workflow;
- care levels and optional care locations;
- care-location occupancy/release handling;
- Vitals, Vaccination and Lab actions;
- Medication, Fluid Therapy, Feeding, Nursing Note, Wound Care, Procedure, Oxygen/Nebulisation, Owner Communication and Other activities;
- billable and stock-affecting activity handling;
- stock posting and stock status tracking;
- charge sheet items and pricing resolution;
- daily stay charges;
- draft invoice synchronization while protecting submitted/paid invoices;
- billing-session aware invoice/payment summaries;
- discharge readiness checks;
- discharge summary, condition, instructions and follow-up fields;
- Active Hospitalisations, Charge Summary, Occupancy, Discharge Watch and Pending Actions reports.

These flows should be adapted, not reimplemented.

## Phase 8 audit findings

### P0 — Hospitalisation save-integrity omissions

Status: partially fixed in this branch.

The shared integrity registries previously omitted `Veterinary Hospitalisation` even though other clinical service DocTypes use them.

Implemented fixes:

- `branch_integrity.py` now treats `service_branch` as required for Hospitalisation;
- `practitioner_integrity.py` now treats `attending_veterinarian` as required and can inherit the practitioner from a linked Consultation;
- the Hospitalisation controller now invokes both integrity services before normal hospitalisation validation;
- backend Doctor-role validation now rejects a non-VetEdge-Doctor as Attending Veterinarian even if a caller bypasses the frontend Link query;
- `patient_service_guard.py` now blocks a transition into Admitted / Under Care / Ready for Discharge when the Patient has subsequently been recorded as deceased.

### P0 — read/list Branch isolation

Status: pending; must be closed before exposing a new EdgeSuite workbench.

`hooks.py` currently provides permission-query conditions for Patient, Appointment, Consultation, Vital Signs, Lab, Vaccination and several other operational DocTypes, but not `Veterinary Hospitalisation`.

The new Hospitalisation Operations page must not compensate for this only in frontend filtering. Add a server-authoritative Hospitalisation permission query / document permission contract so:

- global administrators can see all permitted Branches;
- branch-assigned clinical users see only Hospitalisations within their allowed Branches;
- zero-assignment branch-scoped users fail closed;
- direct form/list/API access cannot bypass the same rule.

This should be completed before broad EdgeSuite exposure.

### P1 — native-form orchestration overload

Status: pending.

The current Hospitalisation DocType client script owns a large collection of grouped buttons/dialogs for Admission, Clinical actions, Stock, Care Location, Billing and Discharge. The workflow works, but the form has become the orchestration layer.

Do not rewrite the DocType or remove the native form immediately. Build an EdgeSuite `Hospitalisation Operations` workbench as the primary operational entrypoint and retain the DocType form as the underlying record/admin fallback until browser QA proves parity.

### P1 — stale UI wording

Status: pending cleanup.

Some Activity field/help text still says billing and stock will be handled by a "later" charge-sheet/invoice flow even though those flows now exist. Update these descriptions during the EdgeSuite migration so the operational UI describes current behavior.

### P1 — report/data-usage architecture

Status: pending optimization.

`hospitalisation_reports.py` currently begins by retrieving matching Hospitalisation names and materializing each full DocType with `frappe.get_doc()` before calculating row data. That is acceptable for small clinic volumes but is not the desired interactive EdgeSuite pattern as data grows.

The new operations workbench should use:

- query-level parent pagination;
- page-only child Activity/Charge aggregates;
- aggregate KPI queries independent of detail-row pagination;
- bounded Link searches;
- no browser-side full-list materialization;
- no polling unless a measured operational requirement justifies it.

The existing Query Reports can remain available during transition, but high-use workbench data should not reuse the current full-materialization path blindly.

### Navigation finding — retired Hospitalisation Dashboard

The source sidebar JSON still contains a legacy `Hospitalisation Dashboard` item, but this is not currently a live runtime defect. `install/dashboard.py` explicitly:

- lists `veterinary-hospitalisation-dashboard` in `REMOVED_STANDARD_PAGES`;
- filters it through `REMOVED_SIDEBAR_LINKS`; and
- deletes the retired Page during synchronization.

Do not resurrect this dashboard. The replacement should be an operational Hospitalisation workbench/action center, not another generic dashboard.

## Recommended implementation sequence

### Phase 8A — security and API foundation

1. Add Hospitalisation permission-query/document permission hooks with Branch fail-closed behavior.
2. Add bounded smart Link search for Patient, Owner, Branch, Attending Veterinarian and Care Location where the workbench needs them.
3. Add a read-only paginated Hospitalisation Operations endpoint:
   - active/all status filter;
   - Branch;
   - Patient/Owner;
   - practitioner;
   - care level/location;
   - invoice/payment/discharge attention filters;
   - max page size 100.
4. Compute page-only Activity/Charge aggregates rather than loading every child table for every matching record.
5. Reuse existing hospitalisation action methods for all mutations; do not duplicate billing/stock/discharge logic.

### Phase 8B — EdgeSuite Hospitalisation Operations page

Create a single-shell EdgeSuite page with:

- Active Hospitalisations default view;
- summary cards: active admissions, Ready for Discharge, pending stock, pending charges/missing prices, blocked discharge/payment attention;
- paginated operational table;
- smart filters;
- click-through to a selected Hospitalisation;
- contextual primary actions based on server-returned capabilities/status;
- no separate Hospitalisation Dashboard.

### Phase 8C — selected Hospitalisation workbench

For a selected admission, expose sections/tabs for:

- Admission/context;
- Care Location;
- Clinical Activities;
- Medication/stock actions;
- Charge Sheet/Billing;
- Discharge readiness and discharge details.

Initially call the existing service APIs/actions. Do not copy their mutation logic into JavaScript.

### Phase 8D — report alignment

Migrate or adapt the five existing hospitalisation reports to the shared Report Center/`EdgeReportShell` pattern where useful:

- Active Hospitalisations;
- Hospitalisation Charge Summary;
- Care Location Occupancy;
- Hospitalisation Discharge Watch;
- Pending Hospitalisation Actions.

Optimize only high-use/high-volume endpoints; bounded operational reports can remain generic if measurement supports that choice.

### Phase 8E — native-form cleanup and parity decision

After browser QA:

- remove stale help text;
- reduce duplicate native buttons only where EdgeSuite parity is proven;
- keep the native DocType available for administration/debugging unless there is a strong reason to hide it;
- do not remove server APIs or accounting safeguards used by both surfaces.

## Safety rules

- Submitted Sales Invoices must never be mutated.
- Posted Stock Entries must not be silently rewritten.
- Billing/session/payment-gate truth remains server-authoritative.
- Branch, practitioner and Patient service validation must be enforced on the backend.
- Care-location assignment must remain Branch/status safe.
- No hidden full-dataset loads.
- No new Hospitalisation Dashboard.

## QA required

### Automated

- Hospitalisation Branch/practitioner/deceased-patient save integrity.
- permission-query Branch isolation including zero-assignment fail closed.
- pagination maximum and page-only child aggregation.
- direct API/form access cannot cross Branch.
- existing admission/payment/discharge tests remain green.
- submitted invoice/posted stock no-mutation regression tests.

### Manual browser

- create from Consultation and direct admission where allowed;
- Admit gate behavior;
- care-location selection/release;
- each clinical activity shortcut;
- medication/stock posting;
- charge generation, draft invoice update and submitted-invoice protection;
- partial/full/no payment gate discharge scenarios;
- multi-Branch visibility;
- mobile/tablet layout;
- request count and transferred bytes for active list and selected admission.
