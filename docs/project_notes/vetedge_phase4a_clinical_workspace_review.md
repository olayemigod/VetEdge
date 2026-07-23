# VetEdge Phase 4A — Veterinary Clinical Workspace Review

## Business Goal

Replace the disconnected native Veterinary Consultation list and form with one action-oriented EdgeSuite UI workspace for consultation capture, clinical findings, treatment planning, vitals, medical-history review, billing access and safe workflow transitions.

## Product Layer

- Product app: VetEdge.
- Shared presentation: standalone `edgesuite_ui` runtime.
- Existing VetEdge services remain authoritative for consultation validation, status transitions, payment gates, dispensary rules, vitals, medical history, treatment defaults and billing.
- CoreEdge is not imported as a frontend or runtime dependency.

## Implemented Scope

- `/app/vetedge-clinical-workspace` Page and collision-safe product bundle.
- Permission-aware Consultation summary, list, search, filters and pagination.
- New and existing Veterinary Consultation capture.
- Patient, service branch, consultation type and VetEdge Doctor selection.
- Presenting complaint, examination notes and assessment notes.
- Symptoms and diagnoses child rows.
- Billing-aware planned-treatment rows.
- Latest vitals summary and new vitals capture through the existing vitals service.
- Patient medical-history modal through the existing medical-history service.
- Existing VetEdge Billing & Payment modal integration.
- Existing Consultation workflow transitions through `transition_consultation_status`.
- Native Consultation List and Form route compatibility.

## Accounting and Stock Safety

- The Clinical Workspace does not create, submit, cancel or directly mutate Sales Invoice, Payment Entry or Stock Entry records.
- Submitted accounting and stock documents are never changed by the workspace.
- Billing actions continue through the existing Billing Modal and Billing Core.
- Consultation payment gates, dispensary gates, completion rules and cancellation resolution continue through existing consultation services.
- Billed treatment rows cannot be changed or removed.
- Consultation-, Laboratory- and Vaccination-generated treatment rows cannot be changed or removed, even while pending billing.
- Browser-supplied source, billing and payment metadata is not trusted for new treatment rows; new rows are classified server-side as `Treatment`, `Pending`, and `Not Billed`.

## Permissions and Context Safety

- Internal users only.
- Permission-aware `frappe.get_list` reads.
- Normal document read, create and write checks.
- Consultation-level access checks.
- Branch-safe list filters and server validation.
- Enabled VetEdge Doctor-only practitioner lookup.
- VetEdge platform-access enforcement on Consultation saves and vitals creation.
- Existing DocType controllers, branch-integrity hooks and practitioner-integrity hooks remain active through normal `doc.insert()` and `doc.save()`.

## Optimistic Locking and Conflict Safety

- Consultation saves require the server `modified` timestamp returned when the workspace opened the record.
- Workflow transitions require the same optimistic timestamp.
- Vitals creation also rejects a stale Consultation snapshot.
- Conflicts instruct the user to refresh rather than overwriting another clinician's changes.

## Independent Loophole Review Findings

1. **New-document route ambiguity**
   - Native Frappe can route a new document as `new-veterinary-consultation-*`.
   - The first route adapter could have treated that temporary name as a saved Consultation.
   - Corrected by explicitly detecting new-document routes and opening `?new=1`.

2. **Optional vitals feature**
   - Loading Consultation detail originally called the vitals service whenever the user had permission.
   - If vitals was disabled in Veterinary Settings, this could block the whole Consultation page.
   - Corrected by checking the vitals feature flag before loading or advertising vitals capability.

3. **Source-generated planned-treatment rows**
   - Billing status alone is not enough to identify immutable rows.
   - Consultation defaults, Laboratory rows and Vaccination rows may still be pending but must remain service-controlled.
   - Corrected with server and frontend source-row protection.

4. **Browser source spoofing**
   - A malicious request could attempt to label a manually added row as Laboratory or Vaccination.
   - Corrected by forcing all new workspace-created rows to `source_type = Treatment` server-side.

5. **Vitals dialog closure**
   - The initial success path attempted to close the dialog while the component was still marked busy.
   - Corrected with a post-success wrapper that closes only after a new vital-sign record is confirmed.

6. **Workflow action order**
   - Existing transition definitions use sets, which can render actions in inconsistent order.
   - Corrected with a deterministic action order while preserving the allowed-transition set.

## Automated Tests

### Static contracts

- Dedicated clinical provider exists and does not use the generic document provider.
- No direct Sales Invoice, Payment Entry or Stock Entry mutation.
- Permission, branch, platform-access and optimistic-lock contracts.
- Existing workflow, vitals, medical-history, treatment-default and billing service reuse.
- Source-generated and billed treatment-row protection.
- Full EdgeSuite component usage and collision-safe asset loading.
- Native Consultation route migration, including new-document routes.

### Live Frappe integration

- Clean Frappe v16 standalone VetEdge site.
- Consultation create, list, detail and update round trip.
- Stale Consultation write rejection.
- Branch-filtered summary.
- Patient and VetEdge Doctor link providers.
- Vitals creation and latest-vitals retrieval.

## Manual QA Checklist

Manual browser QA remains grouped and pending Mathew's QA session.

1. Open Consultation from the product menu, native list route, a named Form route and a notification link.
2. Create a Consultation from scratch and from an Appointment.
3. Confirm Patient, Branch, Consultation Type and Practitioner filtering.
4. Test Doctor, Nurse, Front Desk, Branch Manager, Dispensary User and Administrator permissions.
5. Capture symptoms, diagnoses and treatment rows.
6. Confirm non-doctors cannot add diagnoses or prescribe treatments.
7. Confirm Consultation/Lab/Vaccination source rows and billed rows are read-only.
8. Open Billing & Payment with saved and unsaved Consultation states.
9. Test Full, Partial and No Gate status transitions.
10. Test dispensary-required and dispensary-not-required flows.
11. Record vitals when enabled; confirm Consultation still opens when vitals is disabled.
12. Review medical history and related Laboratory, Vaccination and Hospitalisation links.
13. Trigger a two-user stale-save conflict.
14. Test desktop, tablet and mobile layouts.
15. Verify browser back navigation and unsaved-change confirmation.

## Deferred Items

- Rich-text editing for existing Text Editor fields; Phase 4A currently provides safe text-area capture.
- Dedicated in-workspace Laboratory, Vaccination and Hospitalisation editors; these remain on existing trusted pages until their dedicated phases.
- Final browser acceptance and performance review using real clinic data.

## Status

Implemented on `agent/vetedge-full-edgeui-clinical-workspace-phase4a` under draft PR #21. Automated workflows and clean-site integration must be green before Phase 4A is reported automated-review complete. Manual browser acceptance remains pending.
