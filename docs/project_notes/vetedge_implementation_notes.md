# VetEdge Implementation Notes

This is the living project note for VetEdge implementation status, decisions, known issues, workarounds, risks, and phase progress.

## Update Discipline

This file is not an append-only dump. Whenever future work is completed:

1. Open and read this file first.
2. Search for the relevant section, phase, bug, feature, or known issue.
3. If a matching section exists, update it in place.
4. If a bug was fixed, update the original known issue entry with:
   - fixed status
   - commit hash, when available
   - files changed
   - verification/tests
   - remaining risk, if any
5. If the work changes a previous decision, revise the earlier decision instead of adding a contradictory note.
6. Add a new section only when no relevant section exists.
7. Keep the note organized and readable.
8. Do not append raw completion summaries to the bottom.
9. Include commit hash when available.
10. Include a manual workaround only when it is still relevant.

## Current Status

- Current branch at note creation: `fix/vetedge-drift-bugs`
- Baseline commit at note creation: `f27acc4`
- Context: recent work has focused on stabilizing drift and bug fixes across permissions, UI cleanup, consultation billing, lab workflow, settings behavior, and vaccination pricing/UI cleanup.
- ERPNext remains the source of truth for accounting documents, invoice status, Payment Entry creation, stock, customer, and company records.
- VetEdge service-layer code remains the intended home for veterinary workflow logic. Doctypes should stay thin.

## Phase Progress

### Phase 1 - Permission and Access Drift

Status: recently stabilized.

Summary:
- Permission and branch-access drift has been treated as a server-side concern.
- Branch awareness must remain enforced in service logic and document validation, not only through UI filters.
- Cross-branch treatment remains allowed, but operational branch context must be explicit.

### Phase 2 - UI Labels, Sidebar, and Medical History Cleanup

Status: recently stabilized.

Summary:
- UI copy and labels were cleaned up for clearer clinic workflows.
- Medical history remains patient-centric and VetEdge-owned.
- Medical history must not depend on Marley.

### Phase 3 - Master Pricing Foundation

Status: recently stabilized.

Summary:
- Pricing foundation work supports settings-driven billing behavior.
- Billing must continue to use ERPNext Sales Invoice and Payment Entry.
- Branch to Cost Center mapping remains mandatory for accounting impact.

### Phase 4 / 4B - Consultation Billing Plan and Multiple Invoice Restoration

Status: recently stabilized with remaining historical invoice caveat.

Summary:
- Consultation billing source data is anchored to editable consultation planned treatment rows.
- Manual treatment rows and default consultation fee rows should be visible in `planned_treatments` and use editable row rates before billing.
- Billing Core should not create a hidden default consultation fee when the visible planned row represents that charge.
- Registration billing should not be duplicated inside consultation billing when an active registration invoice/session already exists.
- Ready for Treatment locks clinical order mutation, but Billing / Payment modal state, invoice sync, submit, payment, and historical invoice reads may reconcile existing eligible billing rows under internal billing-sync context.
- Multiple invoice/cycle behavior was restored around draft and submitted invoice boundaries.
- Submitted Sales Invoices must not be mutated by VetEdge.
- Newly added billable rows after a submitted invoice should create or update the next draft/cycle.

### Phase 5 - Consultation Billing Settings

Status: recently stabilized.

Summary:
- Consultation billing enablement and default item auto-add behavior are separate decisions.
- Enabling consultation billing does not force insertion of a default consultation item.
- Default consultation item auto-add remains settings-driven and materializes as a visible planned treatment row when enabled.

### Phase 6A - Lab Result Structure and Settings

Status: recently stabilized.

Summary:
- No new Lab Result DocType is planned for now.
- Lab Order Item remains the storage surface for result data.
- Settings should control workflow behavior without creating duplicate lab result storage.

### Phase 6B - Lab Result Entry and Upload Workflow

Status: recently stabilized.

Summary:
- Lab result entry and uploads remain attached to the lab order item workflow.
- Result entry should preserve source document traceability.
- Lab workflow should avoid duplicating clinical or billing source rows.

### Phase 6C - Lab Order UX Redesign

Status: recently stabilized.

Summary:
- Lab UI uses a full-width workbench pattern.
- Dialogs are used for focused result entry and supporting actions.
- The UX should remain operational and dense enough for clinic staff workflows.

### Phase 6D - Lab Order Workflow and Status Cleanup

Status: recently stabilized.

Summary:
- Lab status handling was cleaned up around practical workflow states.
- Status transitions should remain server-validated.
- Lab workflow decisions should avoid creating extra doctypes unless the storage model truly requires it.

### Phase 7 - Vaccination Workflow Pricing/UI Cleanup

Status: in progress / recently touched.

Summary:
- Vaccination pricing and UI cleanup is part of the recent drift-fix context.
- Standalone Vaccination Records now show `Pricing and Billing` by default; the section is not collapsible.
- Selecting a vaccine auto-loads the billing item, rate, and amount using vaccine defaults first, then Billing Core item price fallback.
- Edited Vaccination Record rates remain the billing source before invoice submission and are protected once the linked invoice is submitted or cancelled.
- Vaccination work must continue to follow ERPNext accounting boundaries.
- Future vaccination changes should preserve branch-aware pricing and source document traceability.

## Billing Core Decisions

- Consultation `planned_treatments` is the editable billing source of truth.
- Source-linked lab and vaccination rows cannot be removed directly from the billing plan unless the source document is cancelled.
- Submitted Sales Invoices must never be mutated by VetEdge.
- New billable rows added after a submitted invoice should create or update the next draft invoice/cycle.
- Satisfied Billing Sessions are historical records, not active billing targets.
- Satisfied Billing Sessions must remain available to workflow payment gates for submitted invoice and partial/full payment evidence; they should not be reopened or shown as active modal sessions.
- Billing group invoice history is a reusable service-level truth separate from the active modal session. It is resolved only from reliable VetEdge links: direct invoice references, service invoice child rows, Billing Sessions, Billing Session Charges, explicit source context, and supported legacy charge evidence. It must not infer ownership from customer, patient, branch, or date alone.
- Consultation payment gates evaluate the consultation billing group invoice collection across child invoice references, source links, Billing Session charge history, and explicitly related service charges. Partial Payment Gate is satisfied when any relevant submitted billing-group invoice has a valid partial or full payment, even if another linked invoice remains outstanding.
- VCON-2026-00069 root cause: Partial Payment Gate was effectively evaluating active/latest session truth instead of billing-group invoice history, so a paid registration-derived invoice could disappear from the consultation gate while a newer pending invoice remained. Implemented fix: `billing_core.get_billing_group_invoice_history(...)` now returns all reliable group invoices for modal history and payment gates, while `billing_modal` keeps closed/satisfied sessions out of active session state. Files changed: `vetedge/services/billing_core.py`, `vetedge/services/billing_modal.py`, `vetedge/tests/test_billing_core.py`, `vetedge/services/test_billing_modal.py`. Verification: billing core and billing modal regression suites cover multiple invoice history, registration-derived consultation invoices, closed session history, and Partial Gate pass/fail messages. Remaining risk: historical invoices missing all VetEdge source/session evidence are intentionally not linked or repaired automatically.
- Follow-up workflow blocker root cause: the Billing / Payment modal used billing-group truth, but legacy consultation validation helpers in `billing.py` could still be called by workflow/proceed paths and ask old invoice/payment resolvers first. Implemented fix: those legacy helpers now consult the canonical source-level Billing Core gate when billing-group invoice evidence exists, and workflow tests assert final-state validation routes through `assert_consultation_can_proceed(...)`. Verification: billing, payment gate, consultation flow, billing core, billing modal, consultation billing plan, lab, and vaccination suites passed. Remaining risk: non-consultation services still using session-level payment gates should be reviewed before applying this same billing-group rule broadly.
- VCON-2026-00070 payment-action/workflow investigation: live diagnostics after paying `ACC-SINV-2026-00131` showed the consultation invoice child rows were physically present, not deleted: `ACC-SINV-2026-00129`, `ACC-SINV-2026-00130`, and `ACC-SINV-2026-00131` remained linked and Billing Group Partial Gate passed with paid evidence from submitted invoices. Hardened fix: `detach_invoice_from_vetedge_sources(...)` now preserves submitted `Consultation Invoice Reference` rows, and billing-group history performs an idempotent reference-only merge for missing consultation invoice rows proven by Billing Session/Charge evidence. Second root cause: the UI Start Consultation button called `consultation_flow.transition_consultation_status(...)`; the initial `assert_consultation_can_proceed(..., "In Progress")` passed, but `doc.save()` re-entered `validate_consultation()` and `validate_registration_payment_before_first_consultation(...)`, which still used active-session-only registration billing logic. Implemented fix: registration payment validation now evaluates `billing_core.get_source_payment_gate_status("Veterinary Patient", patient)` first, so closed/satisfied registration Billing Sessions and their paid invoices satisfy the first-consultation registration gate. Third root cause: Billing Modal totals/counts used billing-group invoice history, but the JavaScript renderer still displayed only the active/latest session invoice list, so the modal could report three linked invoices while rendering one row and mixing active-cycle `Not Invoiced` with billing-group `Partly Paid`. Implemented fix: modal invoice history now renders billing-group invoice rows first, backend rows include `can_open_invoice`, `can_pay_outstanding`, `can_submit_invoice`, `action_label`, and `source_label`, and the UI labels Current Billing Cycle Status separately from Billing Group Payment Status. Verification: modal history tests cover paid/unpaid/draft row actions and JS history rendering. Manual rollback verification for `VCON-2026-00070` confirmed `transition_consultation_status(..., "In Progress")` now returns `In Progress` without the invoice-generation blocker. No submitted Sales Invoice totals/items are changed. Remaining risk: historical invoices missing all VetEdge source/session evidence are intentionally not repaired automatically, and VCON-2026-00070 should still be checked in-browser when practical to confirm row-level buttons render as expected.
- Phase 9A/9B/9C consultation cancellation safety: cancelling a paid/partly paid consultation is a clinical and financial resolution decision, not a simple status change. Implemented behavior: `consultation_cancellation` evaluates Billing Group Invoice History, lab orders, vaccination records, hospitalisation records, Stock Entries, Billing Sessions, notification references, and planned treatment source rows using explicit VetEdge links only. Direct cancellation is blocked when submitted invoices, paid amounts, active hospitalisation, final lab/vaccination records, or submitted stock entries exist; draft invoices and early draft clinical dependencies are returned as warnings. Phase 9B improved the Cancel Consultation UI so the button calls preflight first, renders a structured dialog with cancellation status, blockers, blocking invoices, linked documents, financial resolution options, and separate patient outstanding context. Phase 9C added authoritative safe cancellation execution: preflight is rerun server-side, safe draft current-group invoices are detached/deleted through Billing Core cleanup helpers, current draft Billing Sessions/charges are marked Cancelled where safe, patient outstanding invoices are ignored, and the consultation is saved as Cancelled only after cleanup succeeds. Raw backend transitions to Cancelled route through the same safe execution helper. Submitted Sales Invoices, Payment Entries, Stock Entries, historical Billing Sessions, submitted charge evidence, and consultation invoice history are not mutated or cleared. Tests cover safe cancellation, safe draft invoice/session cleanup, draft invoices from another context being rejected, submitted unpaid/paid/partly paid blockers, patient outstanding context being informational only, transition-path enforcement, friendly financial-resolution labels, and UI section rendering. Remaining risk: Phase 9C does not automate refunds, credit notes, submitted stock reversal, draft clinical dependency cleanup, or notification archival; Phase 9D should define explicit admin/accounting resolution workflows and optional draft clinical cleanup policies.
- Billing Group vs Patient Outstanding Context: current service billing group truth must come only from explicit source evidence such as current consultation invoice references, Billing Session Charges, direct source fields, source markers, or explicitly related service documents. Older invoices for the same patient/customer are informational/action-only and live in a separate patient outstanding context; they must not satisfy the current consultation payment gate or block current consultation cancellation unless explicitly linked into the current billing group. Root cause for the missing/incorrect outstanding display on VCON-2026-00071: a stale consultation invoice child row pointed at `ACC-SINV-2026-00126`, but stronger Billing Session Charge evidence mapped that invoice to `VCON-2026-00068`; the invoice was also already paid with zero outstanding, so it should be excluded from both the current billing group and the patient outstanding section. Implemented fix: billing-group resolution now skips stale direct consultation invoice references when conflicting session/charge evidence points to another consultation, only imports all session invoices when the session context matches the current source, and treats patient outstanding rows as display/action-only. The Billing Modal exposes outstanding rows separately as "Other Outstanding Invoices for this Patient" with clear copy that payment does not count toward the current consultation unless linked. Remaining risk: patient outstanding context uses customer/patient evidence for display convenience only and must not be reused by workflow gates.
- Billing must continue through ERPNext Sales Invoice and Payment Entry.
- VetEdge must not mark invoices paid manually or bypass ERPNext GL.
- Branch to Cost Center mapping remains mandatory for billing.

## Lab Workflow Decisions

- Do not create a new Lab Result DocType for now.
- Lab Order Item remains the storage surface for lab result data.
- Lab UI uses a full-width workbench and dialogs.
- Lab result storage must preserve traceability to the Lab Order and Lab Order Item.
- Lab workflow status changes should be validated server-side.

## Settings Decisions

- Default consultation item auto-add is settings-driven.
- Consultation billing enabled does not force a default consultation item.
- Default consultation item editability is settings-driven and scoped to that default fee row only.
- Settings should enable configurable clinic behavior without hiding accounting or source-document rules.
- Payment integration behavior must remain provider-agnostic and support backend modes such as `stub`, `erpnext_native`, and `processedge_core`.

## Known Issues and Workarounds

### Historical Sales Invoice Posting Date / Due Date Validation

Status: known historical issue; do not spend more time unless newly generated VetEdge invoices also fail through the Billing / Payment modal.

Issue:
Some older VetEdge draft Sales Invoices may still trigger ERPNext submit-time Posting Date / Due Date validation if they bypass VetEdge submit preparation or lack VetEdge linkage markers.

Current decision:
Do not spend more time on this unless newly generated VetEdge invoices also fail through the Billing / Payment modal.

Manual workaround:
Open the Sales Invoice directly, tick Edit Posting Date and Time, set Posting Date and Due Date to today or later, save, then submit.

Fix status:
- Not fixed globally for historical drafts.
- No commit hash yet for a targeted fix.
- Remaining risk: old draft invoices may still need manual correction if they lack VetEdge linkage markers or bypass the prepared VetEdge submission path.

## Fixed Issues

- Recent drift/bug-fix work stabilized permission/access behavior, UI labels, medical history cleanup, master pricing foundations, consultation billing settings, lab result workflow, lab order UX/status cleanup, and vaccination pricing/UI cleanup.
- Future fixed issues should be recorded here only when they do not already have a matching known issue entry above. If a known issue is fixed, update that known issue in place.

## Risks and Revisit Items

- Revisit historical Sales Invoice date validation only if newly generated VetEdge invoices fail through the Billing / Payment modal.
- Continue verifying that submitted invoices are treated as immutable and that new rows after submission create or update the next draft/cycle.
- Confirm source-linked lab and vaccination billing rows cannot be removed directly while their source document remains active.
- Keep Lab Order Item as the lab result storage surface unless a future workflow proves a separate result DocType is necessary.
- Preserve provider-agnostic payment service interfaces and avoid gateway-specific logic in VetEdge modules.
- Maintain global readiness by avoiding country-specific payment gateway, currency, or deployment assumptions.

## Manual QA Checklist

- Confirm consultation billing can create or update draft invoices from `planned_treatments`.
- Confirm submitted invoices are not mutated by later VetEdge billing actions.
- Confirm added billable rows after a submitted invoice move into the next draft/cycle.
- Confirm source-linked lab/vaccination rows are protected from direct removal while the source document is active.
- Confirm consultation billing enabled does not auto-add a default item unless the setting is enabled.
- Confirm lab result entry and uploads remain stored on Lab Order Item.
- Confirm the lab workbench remains full-width and dialog-driven for focused actions.
- Confirm historical draft invoice workaround remains valid only for older affected invoices.
