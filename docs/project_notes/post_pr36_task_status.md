# Post-PR #36 Task Status

| Phase | Status | Immediate outcome |
|---|---|---|
| EdgeSuite Reporting Standard V1 | Structurally implemented — browser QA pending | Shared EdgeSuite runtime remains in PR #19. Stock Expiry and the generic VetEdge Report Center use canonical `EdgeReportShell`; recognized VetEdge dashboards use `EdgeDashboardShell` with compatibility fallback. Report Center now has report-specific bounded smart filters rather than one generic filter set. |
| Standard / Advanced report packaging | Implemented — browser QA pending | Report/dashboard tiering is centralized in `reporting_catalog.py`. Advanced access uses CoreEdge Feature entitlement `advanced_reports` in platform deployments and the existing Veterinary Settings flag for standalone sites. Stock Expiry, Report Center and shared dashboards pass server tier/entitlement metadata into EdgeSuite shells for visible Standard / Advanced / Advanced · Locked state. |
| Export / Print / PDF Foundation | Implementation complete — QA pending | Report and dashboard shells expose opt-in Print/Export only when server-derived capabilities allow them. Stock Expiry has dedicated permission-rechecked export/print endpoints; Current Page export uses the paginated provider and All Filtered synchronous export has a 20,000-row safety ceiling. Report Center uses shell-owned Export/Print controls. |
| Dashboard/report performance hardening | In progress | Consultation dashboard KPIs/charts use database aggregates; Lab and Vaccination dashboard paths reuse aggregate/bounded providers. Shared branch-scoped reporting fails closed when a branch-scoped user has no assigned Veterinary Branch. Revenue Summary and Financial Dashboard remain on the canonical financial dataset because Branch is resolved from clinical links, invoice fields, Payment Entries and cost-center mapping; no simplistic Sales Invoice paginator will replace that accounting-safe resolver. |
| Remaining report migration/optimization | In progress | Planned Treatment, Consultation Register, Laboratory/Lab Order, Vaccination, Owner Register and Patient Register have optimized paginated providers. Further reports are classified by actual volume/value and business safety before dedicated providers are added. |
| VCN / NADIS reporting | Phase 7A implemented — template mapping pending | A read-only paginated NADIS Vaccination source adapter now derives existing regulatory facts from Vaccination + Patient data while explicitly remaining non-submission-ready until the authoritative workbook is mapped. Disease-outbreak audit confirms a dedicated outbreak event model is likely required; consultation diagnoses alone must not be treated as an outbreak. |
| Hospitalisation EdgeSuite completion | Phase 8A implemented — browser QA pending | Hospitalisation security/context gaps are hardened and a read-only EdgeSuite Hospitalisation Operations workbench now provides server-paginated active-admission oversight with bounded filters and page-only Activity/Charge enrichment. Existing clinical/billing mutations remain on the proven Hospitalisation form/services. |
| Training Centre / remaining legacy surfaces | New | Migrate verified remaining native resources. |
| Advanced reporting/intelligence | New | Saved views, drill-through, comparison, grouping, scheduled/exception reporting. |

PR #36 clinical and final consolidation QA remains ongoing and is not duplicated on this continuation branch.

## Stacked branch state

- PR #47 is stacked on `integration/vetedge-current-qa-2026-08` while PR #36 remains open.
- GitHub currently reports PR #47 as Draft and mergeable.
- The synchronized history preserves both PR #36 and continuation patches without force-updating the branch.
- After PR #36 merges, PR #47 must be retargeted/reconciled against `main` and fully revalidated before merge.

## Reference consumer implementation

### Stock Expiry Monitor

- Uses the canonical `EdgeReportShell` for header, filters, insight cards, row table, result count, loading/error/empty states and pagination.
- Keeps query-level server pagination; changing page or page size does not materialize the complete dataset in the browser.
- Warehouse and Item Group use bounded permission-aware search with a 20-row window; Warehouse discovery and validation are constrained by normalized Branch context.
- Item uses permission-aware bounded Link search.
- `Stock Expiry Status` is Advanced and its data/search/Print/Export endpoints recheck entitlement server-side.
- The shell receives `report_tier` and `subscription_entitled` from the server capability context and displays Advanced / Advanced · Locked consistently with actual entitlement.
- Current Page Print/Export uses the interactive paginated provider rather than materializing the complete filtered dataset.
- All Filtered export is a separate server workflow and refuses synchronous materialization above 20,000 matching rows until a queued/chunked large-export path is introduced.
- Submitted ERPNext documents and stock/accounting records are not mutated by reporting actions.

### VetEdge Report Center

- Migrated from manual `EdgePageLayout` + manual table/pagination/action composition to canonical `EdgeReportShell`.
- Provider loading remains product-owned and resolves optimized providers first with Query Report fallback.
- Summary cards, chart slot, result table, result count, loading/error/empty states and pagination are shell-owned.
- Print/Export visibility is derived from `get_shell_capabilities`; locked Advanced reports stop before provider loading and show plan-access state without exposing report data.
- Standard / Advanced / Advanced · Locked tier display is driven by the same server capability response.
- Existing URL filter retention, dashboard return navigation, provider badge and chart rendering are preserved.
- Smart filter definitions cover Consultation Register, Planned Treatment, Laboratory/Lab Order, Vaccination, Patient Register, Owner Register and Service Revenue Breakdown.
- Link discovery is routed through `report_filter_search.py`, capped at 20 results, rechecks report access/entitlement and uses Branch-aware Patient/Owner/practitioner filtering.
- Practitioner choices reuse VetEdge doctor/vaccination staff queries rather than exposing all Users.
- Cascades clear stale combinations: Branch invalidates Patient/Owner/Practitioner, Owner/Patient constrain one another, and Species constrains Breed.
- Planned Treatment explicitly normalizes Report Center `customer` to the backend `owner` filter, preventing a visible Owner filter from being silently ignored.

### Optimized report providers

1. Stock Expiry — query-level server pagination.
2. Planned Treatment — query-level child pagination with scoped consultation parent resolution and aggregate totals.
3. Consultation Register — query-level parent pagination with aggregate insights and page-only enrichment.
4. Laboratory / Lab Order Report — query-level pagination with status aggregates and page-only result timestamp enrichment.
5. Vaccination Report — query-level pagination with server Due Soon/Overdue filtering and aggregates.
6. Owner Register — query-level Customer pagination with branch visibility resolved through patients while preserving all-pet count semantics for each visible owner.
7. Patient Register — query-level Veterinary Patient pagination with database status/species aggregates.

### VetEdge dashboards

- Recognized VetEdge dashboard routes use an `EdgeDashboardShell` compatibility adapter while retaining existing product dashboard body/filter implementations.
- Dashboard Print/Export is opt-in, capability-driven and reauthorized server-side with dashboard scope.
- Executive, Financial, Inventory/Dispensary, Branch Performance and Practitioner Performance are Advanced; Clinical, Lab, Vaccination, Hospitalisation, Boarding and Grooming are Standard.
- The shared adapter passes `report_tier` and `subscription_entitled` into `EdgeDashboardShell`.
- Consultation dashboard metrics use database aggregate queries instead of downloading consultation detail rows. Lab and Vaccination dashboard metrics reuse aggregate providers.
- Dashboard export uses `artifact_kind = dashboard` semantics and a dedicated dashboard document model.
- If the shared dashboard shell is unavailable, the compatibility layer preserves the previous EdgePageLayout rendering path.

## Subscription architecture

- CoreEdge already models plan features as `CoreEdge Entitlement` records and supports `entitlement_type = Feature`; no new subscription DocType is required for report tiers.
- Canonical Advanced feature key: `advanced_reports`.
- Standard reports are included after normal product/role/scope permission checks.
- Advanced reports require normal permission checks plus the Advanced entitlement.
- Shell capability lookup returns locked metadata (`can_view = false`) without exposing report data.
- Actual data, Print and Export endpoints fail closed when Advanced entitlement is absent.
- Mandatory/regulatory NADIS reports are classified as Standard compliance capability; clinics should not require Advanced Reporting entitlement to prepare required submissions.

## Branch/report isolation hardening

- Branch-scoped reporting fails closed if the user has a branch-scoped VetEdge role but no assigned Veterinary Branch. The shared `report_visibility.py` raises `PermissionError` instead of returning unfiltered data.
- Explicit branch requests outside the assigned set are denied.
- One assigned branch remains the automatic default; multiple assigned branches prefer a valid user default and otherwise use a deterministic assigned branch.
- Users with explicit global branch access remain outside the branch-scoped fail-closed gate.
- Smart-filter Branch discovery shows only branches the current user is allowed to select while preserving multi-branch switching.
- Stock Expiry adds a warehouse-scope fail-closed layer so an unmapped Branch or Branch/Warehouse mismatch cannot broaden inventory results.

## Financial reporting optimization boundary

- Revenue Summary currently uses `financial_dataset.py` as accounting/reporting truth.
- Its Branch is not reliably just `Sales Invoice.branch`; resolution may come from linked clinical documents, invoice fields, Payment Entries or cost-center mapping.
- Therefore a simple direct Sales Invoice paginator is intentionally not introduced. Any future dedicated Revenue Summary provider must preserve that complete resolver and submitted-invoice truth before it can replace the canonical dataset path.

## Phase 7A — VCN / NADIS regulatory source foundation

- `nadis_reporting.py` provides a read-only, query-paginated vaccination source endpoint.
- It reuses the established Vaccination Report role/Branch visibility contract and checks Vaccination + Patient read permission.
- Source fields currently available from operational truth include Vaccination Record, administered date/time, Branch, Company, patient/name, owner, species, breed, vaccine, dose, route, batch, batch expiry, practitioner, status and next due date.
- The response explicitly returns `template_mapping_verified = false` and `submission_ready = false`; the normalized source is not represented as the final official workbook.
- Repository audit found no dedicated disease-outbreak DocType. `Consultation Diagnosis` + `Veterinary Diagnosis` can support disease-occurrence surveillance but cannot safely represent a regulatory outbreak event with outbreak-level epidemiological data.
- The detailed mapping/implementation sequence is recorded in `docs/project_notes/vcn_nadis_reporting_plan.md`.
- Attempts to retrieve the previously supplied NADIS workbooks from File Library failed in the current session, and the public-source verification pass did not locate reliable copies. Exact workbook mapping therefore remains a hard gate rather than being guessed.

## Phase 8A — Hospitalisation Operations foundation

- Repository audit confirms the core Hospitalisation workflow already exists: admission/payment gates, care-location occupancy, Vitals, Vaccination, Lab, Medication, Fluid Therapy, Feeding, Nursing Notes, Wound Care, Procedures, Oxygen/Nebulisation, Owner updates, stock posting, Charge Sheet, daily charges, billing-session/invoice integration, discharge readiness and discharge.
- Phase 8 therefore does **not** rebuild those mutations. The first EdgeSuite slice is an operational oversight/workbench layer over the existing source of truth.
- `Veterinary Hospitalisation` now participates in shared required-Branch and required-practitioner save integrity; Attending Veterinarian is backend-validated as a Veterinary Doctor.
- Hospitalisation list/form/API access has a dedicated fail-closed Branch permission hook. Non-global internal users with no assigned Branch see no Hospitalisations and cannot save a Hospitalisation outside their assigned Branches.
- The deceased-Patient service guard now blocks Hospitalisation transitions that commence/continue service (`Admitted`, `Under Care`, `Ready for Discharge`) while preserving historical resolution paths.
- `hospitalisation_context.py` treats Patient.default_branch as a fallback only. A Patient may receive service in another authorised Branch. When a Consultation is linked, that Consultation is authoritative for Patient, Owner, service Branch and Company; missing context is derived server-side and conflicting context is rejected.
- `hospitalisation_operations.py` exposes a read-only, permission-aware parent-paginated operational dataset capped at 100 rows. Child Activity and Charge enrichment is limited to the requested parent page; the endpoint does not loop through `get_doc()` for the entire result set.
- Default operational-active states are exactly `Admitted`, `Under Care` and `Ready for Discharge`; Draft is not counted as an active admission.
- The workbench surfaces active count, Ready for Discharge, Admitted, Under Care and matching-record summary cards plus latest activity, pending stock count, pending charge amount, missing-price count, invoice status and payment-gate status.
- `hospitalisation_filter_search.py` provides 20-row bounded Link search for Branch, Patient, Pet Owner, Attending Veterinarian and Care Location using actual visible Hospitalisation parent records rather than preloading full masters.
- The new `vetedge-hospitalisation-operations` Page uses canonical `EdgeAppShell` + `EdgeReportShell`, server pagination and server visibility context. The enforced default Branch is visible in the filter instead of being hidden behind an apparent All Branches state.
- Phase 8A intentionally keeps Export/Print and operational mutations off the workbench. Clicking operational records opens the existing Hospitalisation/Patient/Owner/Care Location/User record, so current admission/clinical/stock/billing/discharge behavior remains authoritative.
- Recurring sidebar synchronization imports the new Page and replaces the retired `veterinary-hospitalisation-dashboard` item with `Hospitalisation Operations` in the same navigation position without restoring the old dashboard route.

### Phase 8A browser QA required

- Page loads from the Veterinary sidebar without duplicate EdgeSuite/native shell chrome.
- Branch default is visible and multi-Branch switching remains permission-safe.
- Branch → Patient/Owner/Veterinarian/Care Location cascades clear stale values.
- Patient and Owner filters return only values represented in visible Hospitalisation records for the active context.
- Status/Care Level/date filters, pagination and page-size changes return correct totals without full-dataset browser materialization.
- Summary cards remain correct when Status/date/Branch filters change.
- Clicking Hospitalisation, Patient, Owner, Care Location and Attending Veterinarian opens the expected record.
- No Admit, clinical activity, stock, billing or discharge mutation has been duplicated in the workbench.
- Network QA should record request count, response bytes and repeated-navigation cache behavior for the Operations page.

## Current validation state

- VetEdge PR #47 remains Draft and mergeable. No pull-request-triggered VetEdge GitHub Actions workflow has been confirmed for the latest continuation head; source-contract checks must not be reported as CI acceptance.
- EdgeSuite UI PR #19 CI run #378 completed successfully on the current shared report-shell/Link-column checkpoint.
- VetEdge source-contract coverage now also guards Hospitalisation context integrity, read/save Branch isolation, deceased-Patient delivery transitions, operational parent pagination/page-only child enrichment, bounded Hospitalisation filter search, EdgeReportShell workbench adoption, mutation non-duplication and durable replacement of the retired Hospitalisation Dashboard navigation item.
- Browser QA remains required for Stock Expiry filters/pagination/navigation/branch refresh/locked state and notification coexistence.
- Report Center browser QA must verify each smart filter family, cascades, optimized/fallback providers, summaries, charts, pagination, Link drill-through, Standard/Advanced/Locked badges, Print/Export visibility and Back-to-Dashboard navigation.
- Browser/file QA remains required across XLSX, CSV, PDF and Print, including Current Page vs All Filtered, selected columns, raw/presentation mode, chart inclusion and file integrity.
- NADIS browser/workbook QA is not yet applicable to an official export because the authoritative template mapping is still pending.
- Hospitalisation Operations now requires browser/network QA against real active admissions before Phase 8A is accepted.
- Representative dashboard QA must include Executive, Financial and Branch Performance so direct/legacy rendering paths are confirmed to pass through the shared dashboard adapter without duplicated shell chrome.
- The reporting-action settings patch remains idempotent and the synchronized branch preserves PR #36's vaccination consultation billing-edit settings patch.
