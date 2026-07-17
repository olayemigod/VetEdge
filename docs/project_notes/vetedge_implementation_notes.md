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
- Phase 9A/9B/9C consultation cancellation safety: cancelling a paid/partly paid consultation is a clinical and financial resolution decision, not a simple status change. Implemented behavior: `consultation_cancellation` evaluates Billing Group Invoice History, lab orders, vaccination records, hospitalisation records, Stock Entries, Billing Sessions, notification references, and planned treatment source rows using explicit VetEdge links only. Direct cancellation is blocked when submitted invoices, paid amounts, active hospitalisation, final lab/vaccination records, or submitted stock entries exist; draft invoices and early draft clinical dependencies are returned as warnings. Phase 9B improved the Cancel Consultation UI so the button calls preflight first, renders a structured dialog with cancellation status, blockers, blocking invoices, linked documents, financial resolution options, and separate patient outstanding context. Phase 9C added authoritative safe cancellation execution: preflight is rerun server-side, safe draft current-group invoices are detached/deleted through Billing Core cleanup helpers, current draft Billing Sessions/charges are marked Cancelled where safe, patient outstanding invoices are ignored, and the consultation is saved as Cancelled only after cleanup succeeds. Follow-up hardening made cancellation payloads and dialogs use human-friendly labels such as `Consultation Fee`, `Registration Fee`, `Lab Order`, `Vaccination`, and `Invoice ...` instead of internal row names like `4tvh8ar53n`; the safe cancellation result now reports cleaned, skipped, and preserved draft/outstanding invoice references clearly. Draft `Consultation Invoice Reference` cleanup is permission-safe: Billing Core updates the parent `Veterinary Consultation.consultation_invoices` child table and saves the parent document instead of deleting the child DocType row directly. Safe draft Sales Invoice deletion uses a narrow internal cleanup after revalidating that the invoice is draft, current-consultation billing-group evidence only, and not patient outstanding context; submitted invoices never use this bypass and still block cancellation. Raw backend transitions to Cancelled route through the same safe execution helper. Submitted Sales Invoices, Payment Entries, Stock Entries, historical Billing Sessions, submitted charge evidence, and consultation invoice history are not mutated or cleared. Tests cover safe cancellation, safe draft invoice/session cleanup, draft invoices from another context being rejected, submitted unpaid/paid/partly paid blockers, patient outstanding context being informational only, transition-path enforcement, friendly cancellation labels, child-table parent cleanup, narrow draft Sales Invoice cleanup permissions, friendly financial-resolution labels, and UI section rendering. Remaining risk: Phase 9C does not automate refunds, credit notes, submitted stock reversal, draft clinical dependency cleanup, or notification archival; Phase 9D should define explicit admin/accounting resolution workflows and optional draft clinical cleanup policies.
- Phase 9D.1/9D.2 consultation cancellation resolution decisions: paid/partly paid consultation cancellation now has a structured decision and approval layer before any financial workflow proceeds. Added `Veterinary Consultation Cancellation Resolution` to record the consultation, patient, customer, branch, company, selected resolution action, status, reason, selected by/on, optional reschedule links, billing-group paid/outstanding snapshot, and linked invoice snapshot. The service API validates cancellation preflight first, only allows recordable financial actions returned by preflight, limits recording to System Manager, VetEdge Administrator, Branch Manager, Accounts/Cashier, Accounts User, and equivalent VetEdge/accounting roles, prevents overwriting approved/completed decisions, and never creates refunds, credit notes, Payment Entries, Stock Entries, or Sales Invoice reversals. Phase 9D.2 implements the first executable resolution path with approval governance: `Pending Review` means a request/decision has been recorded but is not executable; only an `Approved` `Retain Payment / Clinical Cancellation Only` decision can be executed by an authorized accounting/admin user, and only while the billing group still has submitted invoice plus payment evidence. Execution marks the consultation `Cancelled`, marks the resolution `Completed`, and records that payment was retained with no accounting reversal. Submitted Sales Invoices, Payment Entries, Stock Entries, consultation invoice history, and Billing Group Invoice History are preserved unchanged. The Cancel Consultation dialog now shows an existing decision, shows pending/approved/completed/rejected guidance, offers approval only to authorized roles, and shows `Cancel Clinical Record and Retain Payment` only after approval. Remaining risk: refund, credit, reschedule payment transfer, admin accounting correction, and deeper approval workflow automation remain out of scope; Phase 9D.3 should define the next explicit accounting/admin resolution path.
- Phase 9D.3 reschedule consultation resolution: an approved `Reschedule Consultation` cancellation resolution can now create and link a new `Veterinary Appointment` through the existing consultation follow-up appointment flow, mark the resolution `Completed`, and preserve the old consultation's submitted Sales Invoices, Payment Entries, Stock Entries, consultation invoice history, and Billing Group Invoice History unchanged. Because `Veterinary Consultation.status` does not currently include `Rescheduled`, execution does not force an invalid status or auto-cancel the old consultation; the reschedule relationship is recorded on `Veterinary Consultation Cancellation Resolution.linked_new_appointment`. The UI shows `Create Reschedule Appointment` only for an approved reschedule decision and requires a new appointment date/time with clear copy that payments are not transferred and accounting is not changed. Automatic new-consultation creation, payment transfer, credit note/refund automation, and submitted accounting reversal remain out of scope. Phase 9D.4 should define the next explicit refund/credit/admin correction workflow and decide whether a formal `Rescheduled` consultation status should be added through metadata migration.
- Phase 9D.4 accounting-auditable refund/credit/admin correction foundation: approved `Refund Required`, `Issue Customer Credit`, and `Admin/accounting correction` decisions can now be marked `Completed` only after authorized accounting/admin users record structured accounting evidence: reference type/name, resolution date, completion note, completed by/on, and a positive amount for refund or customer-credit decisions. ERPNext references are verified for existence but never mutated; external/manual references without an ERPNext document are allowed only for System Manager or Accounts Manager. Completion is an audit acknowledgement backed by accounting evidence, not automation: VetEdge does not create Credit Notes, refund Payment Entries, Journal Entries, customer credit, payment transfers, accounting reversals, or apply credit to a rescheduled consultation. Consultation status remains unchanged, and submitted Sales Invoices, Payment Entries, Stock Entries, consultation invoice history, and Billing Group Invoice History are preserved. Doctors and front desk users can view the decision/guidance but cannot complete these accounting resolution acknowledgements. Remaining risk: actual refund, credit note, customer credit allocation, admin correction execution, and any future "Apply Credit to Rescheduled Consultation" workflow must be designed as separate controlled accounting flows.
- Phase 9D.5 financial resolution status effect: refund and customer-credit completion now requires the accounting/admin user to choose a clinical status outcome after accounting evidence is validated. `No Status Change` remains the default for overcharge/correction cases and leaves `Veterinary Consultation.status` unchanged while marking the resolution `Completed`. `Cancel Consultation After Financial Resolution` is allowed only for approved `Refund Required` or `Issue Customer Credit` decisions and only after valid accounting evidence is recorded; it marks the consultation `Cancelled` with a narrow internal cancellation flag that preserves submitted invoices, payments, stock entries, appointment links, billing history, dispensary history, lab/vaccination links, planned treatments, and clinical history. `Admin/accounting correction` supports only `No Status Change` in this phase. VetEdge still does not create Credit Notes, refund Payment Entries, Journal Entries, allocations, accounting reversals, or apply credit to a rescheduled consultation. Remaining risk: post-refund clinical cancellation is now status-only; future phases should define any optional notification/archive policies and controlled automated refund/credit creation if required.
- Phase 9D closeout QA: automated QA passed for consultation cancellation and financial resolution workflows after Phase 9D.5. Verified by tests: safe cancellation with safe draft cleanup, paid/partly paid direct-cancellation blockers, resolution recording as `Pending Review`, approval to `Approved`, retained-payment clinical cancellation to `Cancelled`/`Completed`, reschedule appointment linking with old consultation status unchanged, refund and customer-credit completion with both `No Status Change` and `Cancel Consultation After Financial Resolution`, admin correction completion with no status change only, permission restrictions for doctor/front desk versus accounting/admin roles, Billing Group invoice history preservation, Patient Outstanding Context separation, completed/cancelled consultation history visibility through Billing Modal and related history tests, and scoped latest vitals. No defects were found in the automated pass. Manual browser QA was not run in this closeout pass, so final site-specific UI confirmation remains recommended before marking operational rollout complete.
- Phase 10A.1 cross-service status/history preservation audit: inspected Lab Order, Vaccination Record, Hospitalisation, Grooming, Boarding, Appointment, Billing Modal, Billing Core, and payment gate behavior for final statuses. Backend audit found no submitted Sales Invoice, Payment Entry, Stock Entry, child-row, or link deletion behavior tied to final status transitions. Hospitalisation keeps `Billing / Payment`, payment gate checks, and charge summary visible for `Discharged`/`Cancelled` while blocking unsafe charge sync/stock/discharge actions; appointments preserve service/originating consultation links after `Completed`/`Cancelled`/`No Show`; grooming/boarding service layers preserve linked invoice references and block unsafe terminal transitions. Defects found: `Veterinary Lab Order` hides the shared `Billing / Payment` action when status is `Cancelled`, and `Veterinary Vaccination Record` hides shared `Billing / Payment` for `Administered` and `Cancelled`, leaving only direct `View Invoice` when `linked_invoice` exists. Recommended Phase 10A.2 fix order: restore shared Billing Modal visibility for cancelled lab orders and final vaccination records first, then add focused UI regression tests for final-status billing/history visibility across lab/vaccine/hospitalisation/appointment. Tests run: py_compile for inspected service files, node checks for inspected JS files, and service suites for lab, vaccination, hospitalisation, grooming, boarding, appointment flow, billing modal, billing core, payment gate, registration billing, billing, and vitals. Remaining risk: this was code/test audit only; browser QA should verify role-specific button visibility in the live form layout.
- Phase 10A.2 lab/vaccination final-status billing visibility: restored the shared `Billing / Payment` action for saved Lab Orders including `Cancelled`, and for saved Vaccination Records including `Administered` and `Cancelled`. Unsafe mutation actions remain gated by the existing final-status checks: lab creation/status actions still stop for completed/cancelled/reviewed states, vaccination administration remains limited to `Draft`, `Awaiting Payment`, and `Pending Administration`, and locked billing fields stay read-only for final vaccination states. No backend accounting behavior changed; the shared modal continues to use Billing Core/Billing Group Invoice History for invoice history and payment actions. Regression coverage now guards against reintroducing the old final-status hiding conditions. Remaining risk: browser QA should confirm role-specific custom button grouping on the live Desk form.
- Phase 10A.3 hospitalisation/appointment final-status regression coverage: added tests confirming Hospitalisation final states preserve patient/owner/consultation links, care location, charge rows, activity rows, billing session/invoice references, and stock/material issue references through discharge and cancelled validation paths. Static UI coverage also guards that Hospitalisation keeps `Billing / Payment`, `Check Payment Gate`, and `View Charge Summary` visible for saved records while final statuses continue to block unsafe activity/stock/build/sync actions. Appointment coverage now confirms `Completed`, `Cancelled`, and `No Show` are terminal backend statuses that preserve existing patient/owner/consultation/source links and notes, and that the Appointment UI keeps service/originating consultation history actions available through read-only link fields. No behavior defect was found and no accounting, stock, billing, or workflow service behavior changed. Remaining risk: browser QA should still confirm role-specific final-status button visibility in the live Desk form.
- Phase 10A.4 grooming/boarding/dispensary UI and history audit: inspected Grooming Appointment/Session, Boarding Booking/Stay/Care Record, consultation dispensary stock issue flow, shared Billing Modal/Billing Core adapters, and related tests. Grooming backend statuses are terminal (`Completed`, `Cancelled`, appointment `No Show`) and submitted invoice references are preserved; UI audit found the session shared `Billing / Payment` action was unnecessarily tied to pre-final statuses or `linked_invoice`, so it now remains visible for every saved Grooming Session while terminal statuses still block start/complete/cancel mutation buttons. Boarding backend statuses are terminal for `Checked Out`/`Cancelled` bookings and `Completed` stays; UI audit found cancelled bookings hid shared `Billing / Payment`, and completed stays still exposed `Add Care Record` even though backend care-record validation only allows active stays. The UI now keeps shared Boarding Billing / Payment visible for saved bookings, keeps invoice/stay/history actions visible, and shows `Add Care Record` only while the stay is `Active`. Dispensary/pharmacy is not a standalone DocType in this app; it is a consultation child-table plus Stock Entry flow. Existing service logic blocks re-confirmation for completed/cancelled consultations or when an active Stock Entry exists, preserves dispensed item rows and Stock Entry references, and only reopens dispensary when the linked Stock Entry is cancelled through ERPNext. No submitted Sales Invoice, Payment Entry, or Stock Entry mutation behavior was added. Remaining risk: browser QA should verify role-specific custom button layout for final grooming/boarding records; a future Phase 10A.5 can add deeper integration tests around submitted Stock Entry immutability and final boarding/grooming Billing Modal payloads.
- Phase 10A.5 final-status QA/deeper regression coverage: added Billing Modal payload coverage for final-status Lab Order (`Completed`, `Cancelled`), Vaccination Record (`Administered`, `Cancelled`), Hospitalisation (`Discharged`), Grooming Session (`Completed`, `Cancelled`), and Boarding Booking (`Checked Out`, `Cancelled`). The test verifies source context, Billing Group invoice history, totals, outstanding amount, and per-invoice action metadata are returned without invoking invoice-creation methods. Added dispensary stock immutability coverage proving a completed consultation with a submitted dispensary Stock Entry reference cannot be reconfirmed, does not create a duplicate Stock Entry, and preserves dispensed item rows, batch, posted flag, and Stock Entry reference. Static/browser-style JS coverage from earlier Phase 10A tests continues to guard custom-button conditions for final statuses; no manual browser QA was run in this pass. No new accounting or stock automation was added, and submitted Sales Invoice, Payment Entry, and Stock Entry safety remains owned by ERPNext plus existing VetEdge guards. Remaining risk: live Desk QA with real records is still recommended before operational closeout because automated tests do not inspect role-specific rendered button groups in a browser.
- Phase 10B.1 cross-service Billing Group consistency audit: inspected Billing Core, Billing Modal, payment gate helpers, consultation, registration, lab, vaccination, hospitalisation, grooming, boarding, and dispensary/stock dispensing flows. Result: no high-priority Billing Group consistency defect was found. Active Billing Session remains the action/draft surface resolved from explicit source context, source invoice fields, and Billing Session Charge evidence; Billing Group Invoice History remains the truth surface built from direct source invoice fields, consultation invoice references, Billing Sessions, Billing Session Charges, explicitly related service evidence, and supported registration-derived evidence; Patient Outstanding Context remains customer/patient-based display context only and is marked informational/does-not-satisfy-current-gate. Existing tests cover old patient invoices not satisfying current gates, patient outstanding rows being rendered separately, stale direct invoice references losing to stronger session evidence, related service invoice history, registration-derived invoice gates, final-status modal payloads, submitted document preservation, and safe draft cleanup limits. Module summary: consultation, registration, lab, vaccination, hospitalisation, grooming, and boarding pass the source-explicit billing-group audit; dispensary/pharmacy is not an independent billing-group source in this app and remains a consultation stock/child-row flow with Stock Entry references preserved. Remaining risk: manual Desk QA with legacy production records is still recommended for role-specific button visibility and historical `linked_invoice` rows that predate Billing Session evidence; Phase 10B.2 should add a service-by-service matrix around multiple invoices, old patient outstanding invoices, and legacy source links only where live data exposes gaps.
- Phase 10B.2 Billing Group matrix hardening: added service-by-service regression coverage for consultation, lab, vaccination, hospitalisation, grooming, boarding, registration, dispensary stock references, and shared Billing Modal/Core helpers. The Billing Core matrix now proves multiple explicit current-service invoices are returned once per billing group across the major service doctypes while unrelated old same-patient invoices remain excluded; a legacy direct-link matrix proves `linked_invoice`/`sales_invoice` compatibility only imports the explicitly linked service invoice and does not infer by patient/customer/date. Billing Modal coverage now includes final-status consultation and cancelled hospitalisation payloads, plus a cross-service modal matrix proving current billing-group invoice history and old patient outstanding context remain separate with correct totals/counts. Registration coverage proves an unrelated old patient invoice does not satisfy the first-consultation registration gate when no explicit registration billing-group evidence exists. Dispensary coverage now also proves cancelled consultations preserve posted Stock Entry references without reposting. No service code or Billing Core behavior changed, no accounting/stock automation was added, and submitted Sales Invoices, Payment Entries, Stock Entries, Billing Group history, and Patient Outstanding Context rules remain preserved. Remaining risk: live Desk/browser QA with legacy production records is still needed to verify rendered custom buttons and historical source-link edge cases; Phase 10B closeout should focus on browser/data QA rather than new billing logic.
- Phase 10B.3 Billing Group closeout QA: automated closeout passed for Billing Core, Billing Modal, consultation billing, payment gate, registration billing, lab, vaccination, hospitalisation, grooming, boarding, and dispensary suites after the Phase 10B.2 matrix hardening. Verified rules remain: Active Billing Session is the action/draft surface, Billing Group Invoice History is the truth surface, Patient Outstanding Context is display-only, old patient debt does not satisfy current service gates, final-status modal payloads keep invoice history visible, and dispensary Stock Entry references are preserved without reposting. No defects were found in automated QA and no code fixes were made in this closeout pass. Manual Desk/browser QA was requested but not run because the required in-app browser Node REPL tool was not available in this session; live browser QA remains the open operational closeout item for rendered custom-button behavior and legacy production records. Submitted Sales Invoices, Payment Entries, Stock Entries, billing-group history, and patient outstanding separation remain protected by the passing tests. Phase 10B can be considered code/test closed, with a final live Desk/browser verification recommended before operational rollout sign-off.

### Phase 10C Live Desk Operational QA Checklist

Use this checklist for pre-rollout Desk verification. This is an operational sign-off checklist only; failures should be logged as defects and fixed in a separate implementation phase.

#### Consultation Cancellation Workflow

- Safe unpaid cancellation: confirm preflight allows cancellation, safe draft cleanup runs where applicable, consultation becomes `Cancelled`, and no resolution record is required.
- Paid/partly paid blocker: confirm direct cancellation is blocked, blockers are shown, and consultation status remains unchanged.
- Retain-payment resolution: record request, approve as an authorized role, execute `Cancel Clinical Record and Retain Payment`, confirm consultation becomes `Cancelled`, resolution becomes `Completed`, and submitted invoices/payments remain unchanged.
- Reschedule resolution: record request, approve, create/link new appointment, confirm resolution becomes `Completed`, old consultation status remains unchanged, and no payment/invoice value is moved.
- Refund resolution with no status change: complete with accounting evidence, confirm resolution becomes `Completed`, consultation status remains unchanged, and no refund document is auto-created.
- Refund resolution with cancel outcome: complete with accounting evidence and `Cancel Consultation After Financial Resolution`, confirm consultation becomes `Cancelled` and accounting documents remain unchanged by VetEdge.
- Customer credit with no status change: complete with credit evidence, confirm consultation status remains unchanged and no credit is auto-applied.
- Customer credit with cancel outcome: complete with credit evidence and cancel outcome, confirm consultation becomes `Cancelled` and no credit allocation is created.
- Admin correction: complete with correction evidence, confirm resolution becomes `Completed`, consultation status remains unchanged, and no accounting document is auto-created.
- Role restrictions: verify doctors/front desk can view/request as intended but cannot approve or execute accounting/cancellation resolution actions.

#### Final-Status History Preservation

Confirm history/view sections and links remain visible for:

- Completed Consultation
- Cancelled Consultation
- Completed Lab Order
- Cancelled Lab Order
- Administered Vaccination Record
- Cancelled Vaccination Record
- Discharged Hospitalisation
- Cancelled Hospitalisation
- Completed Grooming Session
- Cancelled Grooming Session
- Checked Out Boarding Booking
- Cancelled Boarding Booking
- Completed Boarding Stay
- Completed Appointment
- Cancelled Appointment
- No Show Appointment
- Consultation with posted dispensary Stock Entry

#### Billing / Payment Modal

For Consultation, Lab Order, Vaccination Record, Hospitalisation, Grooming Session, Boarding Booking, and registration/first-consultation billing context:

- Open `Billing / Payment` from a saved record and confirm the current Billing Group invoice history appears.
- Confirm old patient outstanding invoices appear only under `Other Outstanding Invoices for this Patient`, when present.
- Confirm patient outstanding invoices are not mixed into current Billing Group Invoice History.
- Confirm patient outstanding invoices do not satisfy the current service payment gate.
- Confirm `Open Invoice`, `Pay Outstanding`, `Submit Draft`, and related actions target the intended current-service invoice.
- Confirm final-status records still show invoice history.
- Confirm opening the modal does not create unsafe new invoices for final records.

#### Accounting Safety

For cancellation, billing modal, payment gate, registration, lab, vaccination, hospitalisation, grooming, boarding, and dispensary-related flows:

- Submitted Sales Invoice remains submitted and unchanged.
- Payment Entry remains submitted and unchanged.
- No silent payment allocation or reallocation occurs.
- No Credit Note, refund Payment Entry, or Journal Entry is auto-created unless that specific future workflow is intentionally being tested.
- Billing Group Invoice History remains visible and is not cleared or rewritten as a side effect of status changes.

#### Stock Safety

- Submitted Stock Entry remains submitted and unchanged.
- No duplicate Stock Entry is created by opening history, Billing / Payment, or final-status records.
- Consultation dispensary/stock references remain visible.
- Hospitalisation stock/material issue references remain visible.
- Vaccination stock references remain visible where present.

#### Role and Custom-Button Visibility

Test with these roles where available:

- VetEdge Administrator
- Branch Manager
- Doctor
- Front Desk
- Accounts/Cashier or Accounts User

Confirm:

- View/history buttons are visible to appropriate roles.
- `Billing / Payment` is visible where the workflow supports billing review.
- Accounting completion, approval, and retained-payment execution actions are hidden or blocked for doctors/front desk.
- Unsafe mutation buttons are hidden or backend-blocked in final statuses.
- Role-specific button groups still expose history links for final records.

#### Recommended Test Records to Prepare

- Active consultation with draft invoice.
- Consultation with multiple submitted invoices.
- Completed consultation.
- Cancelled consultation.
- Consultation with old patient outstanding debt.
- Consultation with posted dispensary Stock Entry.
- Completed and cancelled Lab Order with invoice.
- Administered and cancelled Vaccination Record with invoice/stock.
- Discharged Hospitalisation with charges and stock references.
- Cancelled Hospitalisation with existing billing/stock history.
- Grooming Session with invoice.
- Boarding Booking/Stay with charges and care records.
- Completed, cancelled, and no-show Appointment.

#### Sign-Off Table

| Area | Record Tested | Role Tested | Expected Result | Actual Result | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| Paid consultation cancellation |  |  | Block direct cancellation; resolution workflow required |  |  |  |
| Retain-payment cancellation |  |  | Approved decision cancels clinical record only |  |  |  |
| Refund no status change |  |  | Resolution completed; consultation unchanged |  |  |  |
| Refund cancel outcome |  |  | Resolution completed; consultation cancelled |  |  |  |
| Credit no status change |  |  | Resolution completed; consultation unchanged |  |  |  |
| Credit cancel outcome |  |  | Resolution completed; consultation cancelled |  |  |  |
| Admin correction |  |  | Resolution completed; consultation unchanged |  |  |  |
| Final-status Billing / Payment |  |  | Billing Group history visible; no unsafe invoice creation |  |  |  |
| Patient outstanding separation |  |  | Other patient debt shown separately only |  |  |  |
| Dispensary Stock Entry preservation |  |  | Stock reference visible; no duplicate Stock Entry |  |  |  |
| Hospitalisation billing/stock history |  |  | Charges, invoices, and stock refs visible |  |  |  |
| Role/custom-button visibility |  |  | History visible; unsafe actions hidden/blocked |  |  |  |

#### Rollout Rule

Do not mark VetEdge cancellation/billing stabilization as operationally signed off until live Desk QA has at least one pass for these critical flows: paid consultation cancellation, refund/credit status outcome, final-status Billing / Payment modal, dispensary Stock Entry preservation, and hospitalisation billing/stock history.

### Phase 10D Role and Permission QA

Phase 10D audits VetEdge operational roles against billing, cancellation, stock, final-status history, and supporting ERPNext records. The governing rule remains: operational roles should have enough read/use access to complete their workflow, while Sales Invoice, Payment Entry, Stock Entry, Stock Ledger Entry, and accounting/stock reversals remain controlled by ERPNext permissions plus narrow VetEdge service APIs.

#### Role / Document Matrix Summary

| Role group | VetEdge documents needed | ERPNext support documents needed | Intended write/create scope | Restricted actions |
|---|---|---|---|---|
| System Manager / VetEdge Administrator | All VetEdge operational, settings, billing session, and cancellation resolution records | Customer, Item, UOM, Warehouse, Batch, Sales Invoice, Payment Entry, Stock Entry, Company, Account, Price List, Mode of Payment | Full VetEdge administration, settings, approval, and workflow supervision | ERPNext accounting/stock still follows ERPNext document permissions and docstatus rules |
| Branch Manager | Branch operational records, Billing Sessions, cancellation resolutions, grooming/boarding/hospitalisation supervision | Branch-scoped Customer/Item/Warehouse/Batch/invoice/payment/stock visibility as configured in ERPNext | Branch workflow supervision, cancellation-resolution approval where allowed | No unrestricted submitted accounting or stock mutation through VetEdge |
| VetEdge Doctor | Patient, consultation, vitals, planned treatments, lab/vaccine/hospitalisation context, final-status history | Read/use Item, UOM, Batch, Warehouse, stock availability, relevant invoice summaries | Clinical records and clinical requests where allowed | Cannot approve/complete accounting cancellation resolution; cannot directly submit/cancel Sales Invoice or Payment Entry through VetEdge; cannot confirm dispensary stock issue |
| VetEdge Front Desk | Patient/owner context, appointments, registration/check-in, service scheduling, billing status/history | Customer and billing-status visibility, appointment/service links | Appointment, registration, reschedule execution where allowed | Cannot approve/complete accounting resolution; cannot edit clinical diagnoses/treatment notes |
| Lab Technician | Lab Orders, lab items/results, patient/consultation context | Lab service Items/UOM and patient context | Result entry/upload where allowed | Cannot review as doctor or mutate unrelated accounting |
| Grooming / Boarding users | Grooming appointments/sessions, Boarding bookings/stays/care records, patient/owner links | Service item and billing-history visibility where configured | Service progress/care records within branch and status rules | Cannot gain unrelated accounting power; final statuses block unsafe mutation |
| Accounts User / Accounts Manager / Accounts/Cashier | Billing Sessions, Billing Modal actions, cancellation resolution records | Sales Invoice, Payment Entry, Mode of Payment, Account, Customer, Company, Price List | Billing/payment workflow and accounting-resolution approval/completion as configured | Cannot edit clinical diagnosis/treatment notes; no silent payment reallocation |
| Dispensary / stock roles | Consultation dispensary rows, stock posting context, stock references | Item, Batch, Warehouse, Stock Entry, stock availability | Controlled stock issue/posting through VetEdge/ERPNext flow | Cannot mutate submitted Stock Entry or Stock Ledger Entry |

#### Audit Findings

- `hooks.py` applies VetEdge contextual permission hooks for Patient, Appointment, Consultation, Vital Signs, Lab Order, Vaccination Record, Grooming, Notification, and Sales Invoice access. Sales Invoice access is branch/context-aware but does not replace ERPNext role permission for full form access.
- `permissions.py` centralizes role groups and backend gates for internal staff, branch access, patient access, invoice visibility, payment collection, dispensary confirmation, lab request/result/review, grooming, role bundles, and clinical-entry validation.
- `billing_modal.py` requires internal platform access, source read/access validation, branch validation, and ERPNext Sales Invoice / Payment Entry permissions for submit/payment actions.
- `consultation_cancellation.py` keeps cancellation resolution recording/approval/execution backend-authoritative. Doctors/front desk can view/request where allowed but accounting approval/completion and retained-payment execution are limited to accounting/admin/branch roles. Reschedule execution includes front desk scheduling roles.
- `Veterinary Consultation Cancellation Resolution` metadata gives doctors/front desk read-only access and gives accounting/admin/branch roles write/create access. No submit/cancel/amend permission is exposed on the resolution record.
- Final-status operational DocTypes audited in tests do not expose submit/cancel/amend permissions through VetEdge metadata. Final status should keep history visible while backend service methods remain responsible for blocking unsafe workflow actions.
- `Veterinary Settings` write access remains admin-only; doctors may read settings needed for runtime behavior but cannot edit them.

#### ERPNext Support DocTypes Checked

VetEdge workflows depend on ERPNext/Core access to `Customer`, `Item`, `Item Price`, `UOM`, `Warehouse`, `Batch`, `Sales Invoice`, `Sales Invoice Item`, `Payment Entry`, `Payment Entry Reference`, `Mode of Payment`, `Account`, `Company`, `Branch`, `Price List`, `Stock Entry`, `Stock Ledger Entry`, `Bin`, `File`, `Communication`, and `Comment`. Phase 10D does not grant broad permissions to these doctypes from VetEdge; site role setup must assign read/use access appropriate to each clinic role, while VetEdge service APIs continue to require ERPNext permissions for accounting/stock submission and payment recording.

#### Tests and Remaining Manual QA

- Added permission-matrix regression coverage for cancellation-resolution read/write separation, admin-only settings writes, final-status DocType submit/cancel/amend absence, and billing-session accounts access without accounting docstatus powers.
- Existing backend permission coverage already verifies branch scoping, patient restriction behavior, Sales Invoice diagnostics, payment collection role gates, clinical-entry role gates, lab role gates, grooming role gates, and cancellation approval/execution role restrictions.
- Manual Desk QA is still required with real users for workspace visibility, Link field search/filtering, branch/company user-permission behavior, and ERPNext Role Permission Manager assignments for support DocTypes.
- Recommended next phase: live role-login QA using the Phase 10C checklist plus the Phase 10D role matrix, starting with Doctor, Front Desk, Accounts/Cashier, Branch Manager, Lab Technician, Grooming/Boarding user, and Dispensary/Stock user.

### Phase 10F Report Insights Cards

Status: implemented for existing high-value operational report routes.

Summary:
- Added a reusable backend report-summary pattern for VetEdge operational insight cards. The cards use Frappe Script Report `report_summary` output where possible, so they render above the existing report table without a CoreEdge frontend dependency or a custom table rewrite.
- Enhanced existing report routes for Consultation Register, Lab Order Report, Vaccination Report, Boarding Report, Grooming Report, Patient Register, Revenue Summary, Unpaid Invoice Report, Stock Expiry Status, Active Hospitalisations, Hospitalisation Charge Summary, Care Location Occupancy, Hospitalisation Discharge Watch, and Pending Hospitalisation Actions.
- Added future-safe summary builders for Appointment Report and Missed Appointment Report, but did not create those report routes because they are not present in the current app tree.
- Calculation rules are row-based and filter-aware: summaries are built from the same filtered result rows returned to the report table after existing date, branch, company, patient, owner, practitioner, status, warehouse, and report-specific filters have been applied. Empty datasets return zero-value cards instead of errors.
- Billing cards continue to use current report rows and labels such as `Current Service Outstanding`; they do not merge Patient Outstanding Context into current-service Billing Group truth. No submitted Sales Invoice, Payment Entry, Stock Entry, or Stock Ledger Entry mutation was added.
- Stock Expiry Status keeps the existing report source and chart while expanding the summary strip to include affected items, warehouses, and suggested action.
- Manual QA still required: open each enhanced report in Desk, apply date/branch/company/status filters, confirm cards update with the table, confirm empty states, confirm role-specific report access, and confirm no browser console errors.

### Phase 10E Live Role Login QA Checklist

Use this checklist to verify real Desk behavior with actual users and ERPNext Role Permission Manager/User Permission assignments. This is operational QA only; failures should be logged as defects and fixed separately.

#### Test Users to Prepare

Create one test user for each role group where possible.

| Role group | User email | Assigned roles | Company | Branch | Warehouses | Staff/doctor/lab profile | User Permissions configured | Test status |
|---|---|---|---|---|---|---|---|---|
| VetEdge Administrator |  |  |  |  |  |  |  |  |
| Branch Manager |  |  |  |  |  |  |  |  |
| VetEdge Doctor |  |  |  |  |  |  |  |  |
| VetEdge Front Desk |  |  |  |  |  |  |  |  |
| Lab Technician / Lab User |  |  |  |  |  |  |  |  |
| Grooming User |  |  |  |  |  |  |  |  |
| Boarding User |  |  |  |  |  |  |  |  |
| Accounts/Cashier |  |  |  |  |  |  |  |  |
| Accounts User |  |  |  |  |  |  |  |  |
| Accounts Manager |  |  |  |  |  |  |  |  |
| Stock User / Dispensary User |  |  |  |  |  |  |  |  |
| Read-only / Auditor, if used |  |  |  |  |  |  |  |  |

#### ERPNext Support DocType Permission Checklist

Confirm Role Permission Manager and User Permissions allow required read/use access without granting unsafe accounting or stock powers.

Support DocTypes to check: `Customer`, `Item`, `Item Price`, `UOM`, `Warehouse`, `Batch`, `Stock Entry`, `Stock Ledger Entry`, `Bin`, `Sales Invoice`, `Sales Invoice Item`, `Payment Entry`, `Payment Entry Reference`, `Mode of Payment`, `Account`, `Company`, `Branch`, `Price List`, `File`, `Communication`, and `Comment`.

- Doctor: can read/use relevant Item, Batch, UOM, Warehouse, and stock availability context; cannot directly submit/cancel/amend Sales Invoice, Payment Entry, or unrestricted Stock Entry.
- Front Desk: can use patient/owner/appointment/registration records and view billing status where intended; cannot approve/complete accounting resolution.
- Lab User: can use lab orders/results plus patient/item context; cannot mutate unrelated accounting.
- Grooming/Boarding User: can use service records plus patient/owner/service context; cannot submit/cancel accounting documents.
- Accounts/Cashier: can complete intended billing/payment workflow actions; cannot edit clinical diagnosis or treatment notes.
- Branch Manager: can supervise branch records, reports, and allowed approvals; branch/company restrictions still apply where configured.
- Stock/Dispensary User: can use stock/dispensary context where intended; cannot mutate submitted Stock Entry or Stock Ledger Entry.

#### Workspace and Page Access Checklist

For each role, verify the VetEdge/Veterinary workspace opens, relevant shortcuts/cards are visible, irrelevant admin/platform controls are hidden, final-status records can still be opened, and reports are visible only where appropriate.

- Doctor: Veterinary Patient, Consultation, Medical History, Lab Orders, Vaccination, Vitals, Item/Batch/Warehouse context; no Veterinary Settings write; no accounting completion actions.
- Front Desk: owner/customer registration, patient registration, appointments, check-in, billing status; no accounting approval/completion; no clinical diagnosis edit.
- Accounts/Cashier: Billing / Payment modal, Sales Invoice visibility, Payment Entry visibility/actions where allowed, accounting-resolution completion where authorized; no clinical edit authority.
- Branch Manager: branch records, operational reports, cancellation approval where authorized, branch billing oversight.
- Lab User: Lab Orders, Lab Results, patient/consultation context, lab item context; no unrelated accounting mutation.
- Grooming/Boarding User: grooming/boarding records, patient/owner context, service billing visibility where intended; no accounting submit/cancel.
- Stock/Dispensary User: dispensary/stock context, Item/Batch/Warehouse visibility, Stock Entry view where intended; no unsafe submitted Stock Entry mutation.

#### Link Field Behavior Checklist

For each role and workflow, confirm Link fields are filtered and usable.

- Doctor field shows valid doctors only.
- Patient field shows relevant patients.
- Owner/Customer field shows the correct owner/customer.
- Branch field respects assigned branch.
- Warehouse field shows relevant warehouses.
- Batch field shows batches relevant to item/warehouse where possible.
- Item field shows valid service/stock items.
- Lab Test field shows valid lab tests.
- Vaccine Item/Batch fields show valid vaccine context.
- Grooming/Boarding service fields show relevant service items.
- Payment Mode shows valid modes only for accounts/cashier roles where applicable.
- Dependent fields clear/refresh when parent field changes.
- Backend rejects invalid branch/company/warehouse combinations.
- No lazy all-record loading occurs where contextual filtering is required.

#### Workflow QA by Role

- Doctor: open assigned consultation, view patient/owner/history, add clinical notes where allowed, view Item/Batch/Warehouse stock context, create/request lab/vaccine/treatment where allowed, open final-status consultation history, and confirm accounting actions are hidden/blocked.
- Front Desk: create appointment, check in patient, open billing status, create/update registration where allowed, confirm cancellation accounting buttons are hidden, and confirm diagnosis/treatment edits are blocked.
- Accounts/Cashier: open Billing / Payment, view current Billing Group history, view Patient Outstanding Context separately, pay outstanding where allowed, approve/complete allowed accounting resolution, and confirm clinical edits are blocked.
- Branch Manager: open branch reports, approve allowed cancellation resolutions, view branch billing/operational records, and confirm cross-branch records are restricted where applicable.
- Lab User: open lab order, update/post result where allowed, view patient/consultation context, and confirm billing mutation is not available unless intended.
- Grooming/Boarding User: open service records, complete service actions where allowed, view final-status history, confirm Billing / Payment visibility where allowed, and confirm unrelated accounting submit/cancel is blocked.
- Stock/Dispensary User: view dispensary item rows, view Stock Entry references, post/confirm stock only through the intended controlled flow, and confirm submitted Stock Entry mutation is blocked.

#### Cancellation and Financial Resolution Role QA

- Doctor/front desk can read cancellation resolution but cannot create/write/delete/approve/complete accounting resolution.
- Accounts/admin/branch roles can approve where intended.
- Retain-payment execution requires an authorized role.
- Refund/credit/admin correction completion requires an authorized accounting/admin role.
- External reference exception is allowed only for System Manager or Accounts Manager.
- Reschedule execution follows scheduling role policy.
- Final consultation status outcome buttons follow role policy.

#### Final-Status History Role QA

For each relevant role, confirm final-status records preserve Billing / Payment visibility where appropriate, invoice history, payment status, lab/vaccination links, hospitalisation charges/stock references, grooming/boarding history, appointment links, dispensary Stock Entry references, and clinical notes/history.

Final statuses to test: Completed Consultation, Cancelled Consultation, Completed/Cancelled Lab Order, Administered/Cancelled Vaccination, Discharged/Cancelled Hospitalisation, Completed/Cancelled Grooming Session, Checked Out/Cancelled Boarding Booking, Completed Boarding Stay, and Completed/Cancelled/No Show Appointment.

#### Accounting and Stock Safety Sign-Off

For each role, confirm unauthorized users cannot submit, cancel, or amend Sales Invoice; submit or cancel Payment Entry; silently reallocate Payment Entry; submit Stock Entry outside the controlled flow; cancel/amend submitted Stock Entry; change Stock Ledger Entry; or edit Veterinary Settings.

Also confirm opening Billing / Payment does not mutate submitted documents, opening stock/history views does not repost stock, and final-status records do not create duplicate invoices or Stock Entries.

#### Branch / Company Safety Checklist

- Users see only assigned branch/company records where applicable.
- Link fields respect branch/company context.
- Warehouses are branch/company appropriate.
- Billing / Payment does not pull invoices from another branch as current service truth.
- Patient Outstanding Context is separate and clearly labelled.
- Backend rejects invalid cross-branch operations where expected.

#### Live QA Sign-Off Table

| Role | Test User | Branch/Company | Workflow Tested | Expected Result | Actual Result | Pass/Fail | Issue Link/Fix Needed | Notes |
|---|---|---|---|---|---|---|---|---|
| VetEdge Administrator |  |  |  |  |  |  |  |  |
| Branch Manager |  |  |  |  |  |  |  |  |
| VetEdge Doctor |  |  |  |  |  |  |  |  |
| VetEdge Front Desk |  |  |  |  |  |  |  |  |
| Lab Technician / Lab User |  |  |  |  |  |  |  |  |
| Grooming User |  |  |  |  |  |  |  |  |
| Boarding User |  |  |  |  |  |  |  |  |
| Accounts/Cashier |  |  |  |  |  |  |  |  |
| Accounts User |  |  |  |  |  |  |  |  |
| Accounts Manager |  |  |  |  |  |  |  |  |
| Stock User / Dispensary User |  |  |  |  |  |  |  |  |

#### Rollout Decision Rule

VetEdge role/permission stabilization should not be considered operationally signed off until Doctor users can complete clinical workflow without support DocType permission errors; Front Desk can complete appointment/registration/check-in workflow; Accounts/Cashier can complete billing/payment workflow; Lab, Grooming, Boarding, and Stock/Dispensary users can complete service workflows; unauthorized accounting/stock actions remain blocked; branch/company restrictions are confirmed; and final-status history remains visible across roles.

### Phase 10F Operational QA Data Pack

Phase 10F defines the representative records needed for live Desk operational QA and adds a read-only inventory helper. The goal is to identify usable candidate records on `vetedge.local` or staging without creating, submitting, cancelling, deleting, or repairing business data.

#### Data Pack Purpose

Prepare candidate records for testing cancellation workflows, Billing Group behavior, final-status history visibility, role permissions, stock/dispensary references, and branch/company filtering. Candidate records from the helper are inventory suggestions only; the QA owner must still open and validate each record before using it for sign-off.

#### Read-Only Helper

Helper created: `tools/vetedge_qa_data_inventory.py`.

Run from the bench root:

```bash
cd /home/olayemigod/frappe-bench
env/bin/python apps/vetedge/tools/vetedge_qa_data_inventory.py \
  --site vetedge.local \
  --include-counts \
  --include-samples \
  --output /tmp/vetedge_qa_data_inventory.json
```

Safety limits:

- Read-only inventory only.
- No invoices, payments, stock entries, appointments, consultations, or clinical records are created.
- No submitted Sales Invoice, Payment Entry, Stock Entry, or Stock Ledger Entry is changed.
- Missing scenarios are reported as `missing`; the tool does not invent or backfill records.
- Candidate records are labelled as QA candidates, not validated workflow truth.
- No QA data generator was added in this phase.

#### Required QA Scenario Groups

| Group | Required candidate records |
|---|---|
| Consultation | active no invoice, active draft invoice, submitted unpaid invoice, partly paid invoice, fully paid invoice, completed with invoice history, cancelled with invoice history, multiple linked invoices, old patient outstanding separate from current service, posted dispensary Stock Entry reference |
| Cancellation resolution | retain-payment Pending Review, retain-payment Approved, retain-payment Completed, reschedule with linked appointment, refund Approved with evidence, refund Completed no-status-change, refund Completed cancel outcome, credit Approved with evidence, credit Completed no-status-change, credit Completed cancel outcome, admin correction Completed with evidence |
| Lab | completed with invoice history, cancelled with invoice history, linked to consultation, old patient outstanding separate from current billing group |
| Vaccination | administered with invoice history, cancelled with invoice history, vaccine stock/batch/warehouse context, linked to consultation, old patient outstanding separate from current billing group |
| Hospitalisation | active with charges, discharged with invoice history, cancelled with preserved charges/history, stock/material issue reference, care location/occupancy history, old patient outstanding separate from current billing group |
| Grooming | completed session with invoice history, cancelled session with invoice history, appointment/session linked to patient/owner, old patient outstanding separate from current billing group |
| Boarding | checked-out booking with invoice history, cancelled booking with invoice history, completed stay with care records, boarding with charges, old patient outstanding separate from current billing group |
| Appointment | scheduled, completed linked to consultation, cancelled preserving links/notes, no-show preserving links/notes, reschedule-created appointment linked from cancellation resolution |
| ERPNext support data | Customer/owner, Veterinary Patient, consultation/lab/vaccine/grooming/boarding/dispensary Items, Item Price, UOM, Warehouse, Batch, Mode of Payment, Account, Company, Branch, Price List, Stock Entry, Payment Entry, Sales Invoice, Journal Entry or other accounting evidence reference |
| Test users | VetEdge Administrator, Branch Manager, Doctor, Front Desk, Accounts/Cashier, Accounts User, Accounts Manager, Lab User, Grooming User, Boarding User, Stock/Dispensary User |

#### Actual QA Record Register

| Scenario | Candidate Document | Status | Validated By | Notes |
|---|---|---|---|---|
| Active consultation with no invoice |  |  |  |  |
| Active consultation with draft invoice |  |  |  |  |
| Consultation with submitted unpaid invoice |  |  |  |  |
| Consultation with submitted partly paid invoice |  |  |  |  |
| Consultation with submitted fully paid invoice |  |  |  |  |
| Completed consultation with invoice history |  |  |  |  |
| Cancelled consultation with invoice history |  |  |  |  |
| Consultation with multiple linked invoices |  |  |  |  |
| Consultation with old patient outstanding separate from current service |  |  |  |  |
| Consultation with posted dispensary Stock Entry reference |  |  |  |  |
| Retain-payment resolution Pending Review |  |  |  |  |
| Retain-payment resolution Approved |  |  |  |  |
| Retain-payment resolution Completed |  |  |  |  |
| Reschedule resolution with linked appointment |  |  |  |  |
| Refund Required Approved with accounting evidence |  |  |  |  |
| Refund Required Completed with No Status Change |  |  |  |  |
| Refund Required Completed with Cancel outcome |  |  |  |  |
| Issue Customer Credit Completed with No Status Change |  |  |  |  |
| Issue Customer Credit Completed with Cancel outcome |  |  |  |  |
| Admin Accounting Correction Completed with evidence |  |  |  |  |
| Completed Lab Order with invoice history |  |  |  |  |
| Cancelled Lab Order with invoice history |  |  |  |  |
| Administered Vaccination with invoice history |  |  |  |  |
| Cancelled Vaccination with invoice history |  |  |  |  |
| Discharged Hospitalisation with invoice/stock history |  |  |  |  |
| Completed Grooming Session with invoice history |  |  |  |  |
| Checked-out Boarding Booking with invoice history |  |  |  |  |
| Completed Boarding Stay with care records |  |  |  |  |
| Completed Appointment linked to consultation |  |  |  |  |
| No-show Appointment preserving links/notes |  |  |  |  |

#### Remaining Manual Steps

- Run the helper on the target QA site and save the JSON output with the rollout QA evidence.
- Fill the Actual QA Record Register with selected document names.
- Manually create missing records only through normal Desk workflows; do not use shortcuts that bypass ERPNext accounting or stock.
- Use the Phase 10C and Phase 10E checklists to validate the selected records by role.
- Recommended next phase: live Desk QA execution using the generated inventory plus real role logins.

#### Phase 10F.1 Live Inventory Execution

Root cause of the first live-run failure: direct `env/bin/python` execution from the bench root initialized Frappe with the right site config but left the process working directory at the bench root. Frappe's logger builds site log paths relative to the current working directory, so it attempted to open `/home/olayemigod/frappe-bench/vetedge.local/logs/database.log` instead of the real `/home/olayemigod/frappe-bench/sites/vetedge.local/logs/database.log`.

Fix made: `tools/vetedge_qa_data_inventory.py` now detects the Frappe bench root, initializes with the detected `sites` path, temporarily changes into the `sites` directory for `frappe.connect()`, and restores the original working directory in `finally`. This aligns the standalone helper with Frappe's logger path assumptions while keeping the inventory read-only.

Live command used:

```bash
cd /home/olayemigod/frappe-bench
env/bin/python apps/vetedge/tools/vetedge_qa_data_inventory.py \
  --site vetedge.local \
  --include-counts \
  --include-samples \
  --output /tmp/vetedge_qa_data_inventory.json
python3 -m json.tool /tmp/vetedge_qa_data_inventory.json > /tmp/vetedge_qa_data_inventory.pretty.json
```

Live result on `vetedge.local`: 66 total scenarios, 44 found, 22 missing, 0 not applicable. Output files: `/tmp/vetedge_qa_data_inventory.json` and `/tmp/vetedge_qa_data_inventory.pretty.json`.

Missing QA scenarios from the live inventory:

- Consultation with posted dispensary Stock Entry reference.
- Retain-payment cancellation resolutions in Pending Review, Approved, and Completed states.
- Reschedule cancellation resolution with linked new appointment.
- Refund Required resolutions with Approved evidence, Completed No Status Change, and Completed Cancel outcome.
- Issue Customer Credit resolutions with Approved evidence, Completed No Status Change, and Completed Cancel outcome.
- Admin Accounting Correction Completed with evidence.
- Cancelled Lab Order with invoice history.
- Cancelled Vaccination with invoice history.
- Vaccination linked to consultation.
- Cancelled Hospitalisation with preserved history.
- Hospitalisation with stock/material issue reference.
- Cancelled Grooming Session with invoice history.
- Cancelled Boarding Booking with invoice history.
- Boarding with charges.
- Completed Appointment linked to consultation.
- No-show Appointment preserving links/notes.

Safety confirmation: the helper performed read-only DocType queries and wrote JSON only under `/tmp`; it did not create QA records, invoices, payments, stock entries, appointments, consultations, cancellation resolutions, or mutate submitted accounting/stock documents. Remaining manual QA step: create or identify the missing scenarios through normal Desk workflows before operational sign-off.

### Phase 10G Missing QA Scenario Preparation Plan

Phase 10G is a Desk/manual preparation plan for the 22 missing scenarios reported by the Phase 10F.1 inventory. Do not create records by script. Prepare records only on `vetedge.local` or staging using normal VetEdge and ERPNext workflows.

#### Missing Scenario Summary

- Cancellation resolution examples: retain-payment Pending Review/Approved/Completed, reschedule Completed with linked appointment, refund and customer-credit Approved/Completed variants, and admin correction Completed with evidence.
- Dispensary/stock examples: consultation with posted dispensary Stock Entry reference.
- Cancelled lab/vaccination examples: Cancelled Lab Order with invoice history, Cancelled Vaccination with invoice history, and vaccination linked to consultation.
- Cancelled grooming/boarding examples: Cancelled Grooming Session with invoice history, Cancelled Boarding Booking with invoice history, and Boarding with charges.
- Hospitalisation examples: Cancelled Hospitalisation with preserved history and Hospitalisation with stock/material issue reference.
- Appointment final-status examples: Completed Appointment linked to consultation and No-show Appointment preserving links/notes.
- Accounting evidence examples: Sales Invoice, Payment Entry, Journal Entry, return invoice/credit note, or external accounting reference evidence used only through normal ERPNext/test-site workflow.

#### Scenario Preparation Table

| Scenario Group | Missing Scenario | Why Needed | How To Prepare In Desk | Required Role | Expected Result | Safety Notes | Record Name After Creation | Status |
|---|---|---|---|---|---|---|---|---|
| Cancellation resolution | Retain-payment Pending Review | Confirms request state is visible but not executable | Open paid/partly paid consultation, click Cancel Consultation, select Retain Payment, enter reason, record request only | Accounts/Cashier, Branch Manager, VetEdge Administrator | Resolution `Pending Review`; consultation unchanged | Do not approve or execute this example |  |  |
| Cancellation resolution | Retain-payment Approved | Confirms approval gating | Start from separate Pending Review retain-payment decision and approve with authorized user | Accounts Manager, Branch Manager, VetEdge Administrator | Resolution `Approved`; consultation unchanged | Do not click execute on this example |  |  |
| Cancellation resolution | Retain-payment Completed | Confirms clinical cancel with retained payment | Start from approved retain-payment decision, execute `Cancel Clinical Record and Retain Payment` | Accounts Manager, Branch Manager, VetEdge Administrator | Consultation `Cancelled`; resolution `Completed`; invoices/payments unchanged | Do not refund, credit, or mutate accounting docs |  |  |
| Cancellation resolution | Reschedule Completed with linked appointment | Confirms reschedule link workflow | Record and approve Reschedule Consultation, then create reschedule appointment from dialog | Front Desk or authorized admin/accounts role | Resolution `Completed`; linked new appointment set; old consultation unchanged | Do not transfer payment or invoice value |  |  |
| Cancellation resolution | Refund Required Approved with accounting evidence | Confirms approved refund evidence state | Record Refund Required, approve, enter/verify accounting evidence but keep example before completion if possible | Accounts Manager / Accounts User | Resolution `Approved`; evidence available for completion test | Use normal ERPNext evidence only; do not create by script |  |  |
| Cancellation resolution | Refund Required Completed with No Status Change | Tests financial completion without clinical cancellation | Complete approved refund resolution with valid evidence and choose Keep consultation unchanged | Accounts Manager / Accounts User | Resolution `Completed`; consultation unchanged | Do not auto-create refund docs through VetEdge |  |  |
| Cancellation resolution | Refund Required Completed with Cancel outcome | Tests financial completion plus clinical cancellation | Complete approved refund resolution with valid evidence and choose Cancel Consultation After Financial Resolution | Accounts Manager / Accounts User | Resolution `Completed`; consultation `Cancelled`; accounting docs unchanged | Use only test/staging accounting evidence |  |  |
| Cancellation resolution | Issue Customer Credit Approved with accounting evidence | Confirms credit approval/evidence state | Record Issue Customer Credit, approve, identify evidence, leave uncompleted if possible | Accounts Manager / Accounts User | Resolution `Approved`; consultation unchanged | Do not apply credit to rescheduled consultation |  |  |
| Cancellation resolution | Issue Customer Credit Completed with No Status Change | Tests credit completion without clinical cancellation | Complete approved credit decision with evidence and No Status Change | Accounts Manager / Accounts User | Resolution `Completed`; consultation unchanged | Do not auto-allocate credit |  |  |
| Cancellation resolution | Issue Customer Credit Completed with Cancel outcome | Tests credit completion plus clinical cancellation | Complete approved credit decision with evidence and Cancel outcome | Accounts Manager / Accounts User | Resolution `Completed`; consultation `Cancelled`; invoices/payments unchanged | No payment transfer or automatic allocation |  |  |
| Cancellation resolution | Admin Accounting Correction Completed with evidence | Tests admin correction acknowledgement | Record admin correction, approve, complete with correction evidence/reference | Accounts Manager, VetEdge Administrator, System Manager | Resolution `Completed`; consultation unchanged | Admin correction cannot use cancel outcome in this phase |  |  |
| Dispensary / stock | Consultation with posted dispensary Stock Entry reference | Tests stock reference visibility and immutability | Use normal consultation treatment/dispensary flow, select stock Item/Batch/Warehouse, confirm issue through VetEdge | Stock/Dispensary User | Submitted Stock Entry linked on dispensed child row | Do not repost or edit submitted Stock Entry manually |  |  |
| Lab | Cancelled Lab Order with invoice history | Tests final-status billing/history visibility | Create lab order, create Billing / Payment history, cancel through normal lab workflow | Doctor/Lab User plus Accounts/Cashier | Lab Order `Cancelled`; Billing / Payment and invoice history visible | Do not delete or detach invoice links |  |  |
| Vaccination | Cancelled Vaccination with invoice history | Tests final-status billing/history visibility | Create vaccination, create Billing / Payment history, cancel through normal workflow | Doctor/Vaccination staff plus Accounts/Cashier | Vaccination `Cancelled`; invoice history visible | Preserve vaccine/billing context |  |  |
| Vaccination | Vaccination linked to consultation | Tests consultation-scoped vaccine history | Create vaccination from consultation action | Doctor / Vaccination staff | Vaccination has consultation link | Use normal consultation flow only |  |  |
| Grooming | Cancelled Grooming Session with invoice history | Tests final-status service billing visibility | Create grooming session, create billing history, cancel through normal workflow | Grooming User / Branch Manager | Session `Cancelled`; Billing / Payment visible | Do not submit/cancel accounting docs manually |  |  |
| Boarding | Cancelled Boarding Booking with invoice history | Tests final-status booking billing visibility | Create booking, create billing history, cancel through normal workflow | Front Desk / Boarding User / Branch Manager | Booking `Cancelled`; invoice history visible | Preserve charges/history |  |  |
| Boarding | Boarding with charges | Tests charge/history visibility | Create boarding booking/stay and add charges through normal boarding workflow | Boarding User / Branch Manager | Boarding charges visible and billable | Do not hand-edit submitted invoices |  |  |
| Hospitalisation | Cancelled Hospitalisation with preserved history | Tests cancelled final history | Admit/create hospitalisation, add charges/activities, cancel through normal workflow | Doctor / Branch Manager | Hospitalisation `Cancelled`; charge/activity links preserved | Do not delete child rows |  |  |
| Hospitalisation | Hospitalisation with stock/material issue reference | Tests hospitalisation stock visibility | Use controlled hospitalisation stock/material issue flow | Doctor/Nurse/Stock User | Stock/material reference visible; submitted Stock Entry unchanged | Do not edit submitted Stock Entry |  |  |
| Appointment | Completed Appointment linked to consultation | Tests appointment/consultation link preservation | Create appointment, check in/start consultation, complete appointment through normal workflow | Front Desk / Doctor | Appointment `Completed`; consultation link visible | Do not unlink consultation |  |  |
| Appointment | No-show Appointment preserving links/notes | Tests no-show final status history | Create appointment, add notes/reason, mark No Show through normal workflow | Front Desk / Branch Manager | Appointment `No Show`; patient/owner/notes preserved | Do not delete linked service records |  |  |

#### Desk Preparation Guidance

Cancellation resolution scenarios:

- Start from separate paid or partly paid consultations so each status example can remain available for QA.
- Use `Cancel Consultation` to record the resolution request.
- Approve only with authorized Accounts/Admin/Branch roles.
- Complete only where accounting evidence exists and the scenario requires completion.
- Do not create artificial accounting documents unless this is a local/staging site and the document is created through normal ERPNext workflow.
- Record every consultation, resolution, invoice, payment, and evidence reference in the QA register.

Dispensary / stock scenario:

- Use the normal consultation/dispensary workflow.
- Select a valid stock Item, Batch, and Warehouse.
- Post stock only through the controlled VetEdge flow.
- Confirm the Stock Entry is submitted and the consultation child row keeps the Stock Entry reference.
- Do not repost, cancel, amend, or manually edit the submitted Stock Entry.

Lab and vaccination scenarios:

- Create records through the normal consultation or standalone service flow.
- Create invoice/billing history through `Billing / Payment`.
- Cancel records only through the normal workflow.
- Confirm `Billing / Payment`, invoice history, vaccine/lab context, and consultation links remain visible after cancellation.

Grooming and boarding scenarios:

- Use normal grooming/boarding workflows.
- Create billing history before cancelling when the scenario requires invoice history.
- For boarding charges, add charges through the supported boarding charge workflow.
- Confirm history buttons remain visible and unsafe final-status actions remain blocked.

Hospitalisation scenarios:

- Admit or create hospitalisation through the normal hospitalisation flow.
- Add charge/activity rows and care/location history where applicable.
- Post stock/material issue only through the controlled hospitalisation stock workflow.
- Cancel/discharge through normal workflow and confirm billing, stock, charge, activity, and location history remain visible.

Appointment scenarios:

- Create appointments through the scheduler.
- For completed linked appointment, check in/start consultation and complete through the normal flow.
- For no-show, add notes/reason and mark No Show through the normal appointment workflow.
- For reschedule-created appointment, use the cancellation resolution reschedule flow and record the linked appointment name.

Accounting evidence examples:

- Use existing test/staging Sales Invoice, Payment Entry, Journal Entry, return invoice/credit note, or external evidence where appropriate.
- If evidence must be created, create it only through normal ERPNext workflow on local/staging.
- Submitted accounting documents must remain unchanged after being referenced as evidence.

#### Role Assignment for Preparation

- VetEdge Administrator: overall setup, settings visibility, emergency supervision.
- Branch Manager: branch approvals, operational supervision, hospitalisation/grooming/boarding oversight.
- Doctor: consultation, clinical notes, lab/vaccination requests, hospitalisation clinical flow.
- Front Desk: appointment creation, check-in, reschedule appointment creation, boarding/grooming scheduling where applicable.
- Accounts/Cashier / Accounts User: Billing / Payment, invoice/payment evidence, normal payment actions.
- Accounts Manager: refund/credit/admin correction approval and external evidence exception where allowed.
- Lab User: lab result/history preparation.
- Grooming/Boarding User: service progress, cancellation/completion scenarios.
- Stock/Dispensary User: controlled stock issue and Stock Entry reference preparation.

#### Safety Rules

- Prepare only on `vetedge.local` or staging.
- Do not run on production.
- Do not mutate submitted Sales Invoices, Payment Entries, Stock Entries, or Stock Ledger Entries manually.
- Do not create records by script.
- Use normal Desk workflows only.
- Do not use old patient outstanding invoices as current-service billing truth.
- Record all document names in the QA register.
- Rerun the read-only inventory after preparation and compare found/missing counts.

#### Rerun Inventory Command

```bash
cd /home/olayemigod/frappe-bench
env/bin/python apps/vetedge/tools/vetedge_qa_data_inventory.py \
  --site vetedge.local \
  --include-counts \
  --include-samples \
  --output /tmp/vetedge_qa_data_inventory.json

python3 -m json.tool /tmp/vetedge_qa_data_inventory.json > /tmp/vetedge_qa_data_inventory.pretty.json
```

#### Missing Scenario QA Record Register

| Scenario | Required Status | Prepared Record Name | Linked Invoice | Linked Payment Entry | Linked Stock Entry | Prepared By | Date | Verified By | Pass/Fail | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| Consultation with posted dispensary Stock Entry reference | Consultation with submitted Stock Entry child reference |  |  |  |  |  |  |  |  |  |
| Retain-payment resolution Pending Review | Resolution Pending Review |  |  |  |  |  |  |  |  |  |
| Retain-payment resolution Approved | Resolution Approved |  |  |  |  |  |  |  |  |  |
| Retain-payment resolution Completed | Consultation Cancelled; resolution Completed |  |  |  |  |  |  |  |  |  |
| Reschedule resolution with linked appointment | Resolution Completed with linked appointment |  |  |  |  |  |  |  |  |  |
| Refund Required Approved with evidence | Resolution Approved with evidence available |  |  |  |  |  |  |  |  |  |
| Refund Required Completed with No Status Change | Resolution Completed; consultation unchanged |  |  |  |  |  |  |  |  |  |
| Refund Required Completed with Cancel outcome | Resolution Completed; consultation Cancelled |  |  |  |  |  |  |  |  |  |
| Issue Customer Credit Approved with evidence | Resolution Approved with evidence available |  |  |  |  |  |  |  |  |  |
| Issue Customer Credit Completed with No Status Change | Resolution Completed; consultation unchanged |  |  |  |  |  |  |  |  |  |
| Issue Customer Credit Completed with Cancel outcome | Resolution Completed; consultation Cancelled |  |  |  |  |  |  |  |  |  |
| Admin Accounting Correction Completed with evidence | Resolution Completed; consultation unchanged |  |  |  |  |  |  |  |  |  |
| Cancelled Lab Order with invoice history | Lab Order Cancelled |  |  |  |  |  |  |  |  |  |
| Cancelled Vaccination with invoice history | Vaccination Cancelled |  |  |  |  |  |  |  |  |  |
| Vaccination linked to consultation | Vaccination has consultation link |  |  |  |  |  |  |  |  |  |
| Cancelled Hospitalisation with preserved history | Hospitalisation Cancelled |  |  |  |  |  |  |  |  |  |
| Hospitalisation with stock/material issue reference | Hospitalisation has stock reference |  |  |  |  |  |  |  |  |  |
| Cancelled Grooming Session with invoice history | Grooming Session Cancelled |  |  |  |  |  |  |  |  |  |
| Cancelled Boarding Booking with invoice history | Boarding Booking Cancelled |  |  |  |  |  |  |  |  |  |
| Boarding with charges | Booking/stay has charges |  |  |  |  |  |  |  |  |  |
| Completed Appointment linked to consultation | Appointment Completed with consultation link |  |  |  |  |  |  |  |  |  |
| No-show Appointment preserving links/notes | Appointment No Show with notes/context |  |  |  |  |  |  |  |  |  |

#### Completion Rule

Phase 10G is complete when every missing scenario has either a prepared record name or a documented deferral reason, the read-only inventory has been rerun, missing count is reduced or explained, no data was created outside normal Desk workflow, and no submitted accounting or stock document was manually mutated.

### Phase 10H Operational QA Execution Report

Phase 10H records the operational QA execution status after rerunning the read-only inventory. In this pass, the inventory was executed successfully, but live Desk role-login QA was not performed in this session and the Phase 10G missing scenarios remain missing. No product code was changed, no records were created by script, and no accounting or stock documents were mutated.

#### Inventory Summary

| Run Date | Site | Total Scenarios | Found | Missing | Not Applicable | Output File | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 2026-07-07 | `vetedge.local` | 66 | 44 | 22 | 0 | `/tmp/vetedge_qa_data_inventory.json`; `/tmp/vetedge_qa_data_inventory.pretty.json` | Read-only inventory rerun succeeded. Missing scenarios are unchanged from Phase 10F.1 and require Desk/manual preparation before rollout sign-off. |

Remaining missing scenarios:

- Consultation with posted dispensary Stock Entry reference.
- Retain-payment cancellation resolutions in Pending Review, Approved, and Completed states.
- Reschedule cancellation resolution with linked new appointment.
- Refund Required resolutions with Approved evidence, Completed No Status Change, and Completed Cancel outcome.
- Issue Customer Credit resolutions with Approved evidence, Completed No Status Change, and Completed Cancel outcome.
- Admin Accounting Correction Completed with evidence.
- Cancelled Lab Order with invoice history.
- Cancelled Vaccination with invoice history.
- Vaccination linked to consultation.
- Cancelled Hospitalisation with preserved history.
- Hospitalisation with stock/material issue reference.
- Cancelled Grooming Session with invoice history.
- Cancelled Boarding Booking with invoice history.
- Boarding with charges.
- Completed Appointment linked to consultation.
- No-show Appointment preserving links/notes.

#### Scenario Execution Table

| Scenario | Record Name | Role Tested | Expected Result | Actual Result | Pass/Fail | Issue/Fix Needed | Notes |
|---|---|---|---|---|---|---|---|
| Safe unpaid cancellation | Not executed | Not executed | Consultation becomes `Cancelled`; no resolution required; safe draft cleanup only | Pending live Desk QA | Pending | Prepare/test record | Inventory alone cannot verify workflow execution. |
| Paid/partly paid cancellation blocker | Not executed | Not executed | Direct cancellation blocked; financial resolution options shown; consultation unchanged | Pending live Desk QA | Pending | Prepare/test record | Requires paid/partly paid consultation and role login. |
| Retain-payment resolution | Missing scenario records | Not executed | Pending Review -> Approved -> Completed; consultation cancels only after approved execution | Pending preparation | Pending | Prepare missing resolution examples | Missing in inventory. |
| Reschedule resolution | Missing scenario record | Not executed | Approved reschedule creates linked appointment; old consultation unchanged | Pending preparation | Pending | Prepare missing resolution example | Missing in inventory. |
| Refund Required outcomes | Missing scenario records | Not executed | Evidence required; Completed with selected status outcome; no automatic accounting document creation | Pending preparation | Pending | Prepare missing refund examples | Missing in inventory. |
| Issue Customer Credit outcomes | Missing scenario records | Not executed | Evidence required; Completed with selected status outcome; no credit allocation | Pending preparation | Pending | Prepare missing credit examples | Missing in inventory. |
| Admin Accounting Correction | Missing scenario record | Not executed | Evidence required; Completed; consultation unchanged; cancel outcome not allowed | Pending preparation | Pending | Prepare missing admin correction example | Missing in inventory. |
| Billing Group QA across services | Candidate records partially available | Not executed | Current group history visible; patient outstanding separate; final statuses show history | Pending live Desk QA | Pending | Use inventory candidates and prepare missing final-status records | Inventory is not a browser/modal execution test. |
| Final-status history QA | Candidate records partially available | Not executed | History visible; unsafe actions blocked | Pending live Desk QA | Pending | Prepare missing cancelled/final-status records | Missing cancelled lab/vaccine/grooming/boarding/hospitalisation examples. |
| Stock/dispensary QA | Missing scenario record | Not executed | Submitted Stock Entry reference visible and immutable | Pending preparation | Pending | Prepare posted dispensary Stock Entry consultation | Missing in inventory. |
| Branch/company QA | Not executed | Not executed | Branch/company filters and backend checks respected | Pending live role-login QA | Pending | Test with assigned branch users | Requires role-login QA. |

#### Role Login QA Table

| Role | User | Branch/Company | Workflows Tested | Pass/Fail | Permission Issues | Notes |
|---|---|---|---|---|---|---|
| VetEdge Administrator | Not executed |  |  | Pending | Not tested | Requires live login. |
| Branch Manager | Not executed |  |  | Pending | Not tested | Requires live login. |
| VetEdge Doctor | Not executed |  |  | Pending | Not tested | Must verify Item/Batch/UOM/Warehouse context and blocked accounting actions. |
| VetEdge Front Desk | Not executed |  |  | Pending | Not tested | Must verify appointment/registration/check-in and blocked accounting resolution. |
| Accounts/Cashier | Not executed |  |  | Pending | Not tested | Must verify Billing / Payment and blocked clinical edits. |
| Accounts User | Not executed |  |  | Pending | Not tested | Must verify permitted payment/accounting resolution actions. |
| Accounts Manager | Not executed |  |  | Pending | Not tested | Must verify approval/completion and external evidence exception where applicable. |
| Lab User / Lab Technician | Not executed |  |  | Pending | Not tested | Must verify lab result workflow and no unrelated accounting mutation. |
| Grooming User | Not executed |  |  | Pending | Not tested | Must verify grooming workflow and final-status history. |
| Boarding User | Not executed |  |  | Pending | Not tested | Must verify boarding workflow and final-status history. |
| Stock/Dispensary User | Not executed |  |  | Pending | Not tested | Must verify controlled stock posting and blocked submitted Stock Entry mutation. |

#### Accounting / Stock Safety Table

| Document Type | Sample Document | Before State | After State | Mutated? | Pass/Fail | Notes |
|---|---|---|---|---|---|---|
| Sales Invoice | Not sampled in live Desk QA | Not recorded | Not recorded | No mutation by inventory helper | Pending live QA | Inventory helper performs read-only queries only. |
| Payment Entry | Not sampled in live Desk QA | Not recorded | Not recorded | No mutation by inventory helper | Pending live QA | No payment allocation/reallocation tested in Desk. |
| Stock Entry | Not sampled in live Desk QA | Not recorded | Not recorded | No mutation by inventory helper | Pending live QA | Posted dispensary/hospitalisation stock scenarios still missing. |
| Stock Ledger Entry | Not sampled in live Desk QA | Not recorded | Not recorded | No mutation by inventory helper | Pending live QA | No direct stock ledger test performed. |

#### Defect Register

| Defect ID | Area | Severity | Record/User | Description | Suggested Fix | Status |
|---|---|---|---|---|---|---|
| QA-10H-001 | QA data readiness | Medium | Inventory output | 22 required operational QA scenarios are still missing, so live QA cannot be completed end-to-end. | Prepare missing records through Phase 10G Desk workflows and rerun inventory. | Open |
| QA-10H-002 | Live role-login QA | Medium | Role users | No live role-login QA results were supplied or executed in this session. | Execute Phase 10E checklist with real users and record pass/fail results. | Open |

#### Rollout Decision

Decision: **Blocked pending missing QA records**.

Reason: the read-only inventory runs successfully and no data mutation occurred, but 22 required QA scenarios are still missing and live Desk role-login QA has not been executed. VetEdge should not be operationally signed off until the missing scenario records are prepared or explicitly deferred, the inventory is rerun, role-login QA is completed, and accounting/stock safety is verified against real sample documents.

### Phase 10I Missing QA Records Preparation Status

Phase 10I was requested to prepare or identify the 22 missing scenarios through normal Desk workflows only. No Desk records were prepared in this session because no live Desk login/session and role-user details were available to perform manual workflows. To preserve the safety rules, no records were created by script, no generator was added, no product code was changed, and no submitted accounting or stock document was manually mutated.

#### Inventory Before / After

| Run Date | Site | Total Scenarios | Found | Missing | Not Applicable | Output File | Notes |
|---|---|---:|---:|---:|---:|---|---|
| 2026-07-07 before preparation | `vetedge.local` | 66 | 44 | 22 | 0 | `/tmp/vetedge_qa_data_inventory.json` | Baseline from Phase 10H. |
| 2026-07-07 after attempted preparation | `vetedge.local` | 66 | 44 | 22 | 0 | `/tmp/vetedge_qa_data_inventory.json`; `/tmp/vetedge_qa_data_inventory.pretty.json` | No Desk preparation was performed in this session; missing scenarios unchanged. |

#### Prepared / Identified Records

| Scenario | Prepared Record Name | Linked Invoice | Linked Payment Entry | Linked Stock Entry | Status | Reason / Next Step |
|---|---|---|---|---|---|---|
| Consultation with posted dispensary Stock Entry reference |  |  |  |  | Deferred | Requires normal Desk consultation/dispensary workflow with stock item, batch, warehouse, and controlled stock posting. |
| Retain-payment resolution Pending Review |  |  |  |  | Deferred | Requires paid/partly paid consultation and Cancel Consultation dialog. |
| Retain-payment resolution Approved |  |  |  |  | Deferred | Requires authorized approval through Desk. |
| Retain-payment resolution Completed |  |  |  |  | Deferred | Requires approved retain-payment decision and authorized execution through Desk. |
| Reschedule resolution with linked appointment |  |  |  |  | Deferred | Requires approved reschedule resolution and appointment creation through Desk. |
| Refund Required Approved with evidence |  |  |  |  | Deferred | Requires accounting evidence prepared through normal ERPNext/test workflow. |
| Refund Required Completed with No Status Change |  |  |  |  | Deferred | Requires approved refund decision, evidence, and completion through Desk. |
| Refund Required Completed with Cancel outcome |  |  |  |  | Deferred | Requires separate approved refund decision, evidence, and cancel outcome through Desk. |
| Issue Customer Credit Approved with evidence |  |  |  |  | Deferred | Requires accounting evidence prepared through normal ERPNext/test workflow. |
| Issue Customer Credit Completed with No Status Change |  |  |  |  | Deferred | Requires approved credit decision, evidence, and completion through Desk. |
| Issue Customer Credit Completed with Cancel outcome |  |  |  |  | Deferred | Requires separate approved credit decision, evidence, and cancel outcome through Desk. |
| Admin Accounting Correction Completed with evidence |  |  |  |  | Deferred | Requires approved admin correction decision and correction evidence. |
| Cancelled Lab Order with invoice history |  |  |  |  | Deferred | Requires lab order, Billing / Payment history, and normal cancellation through Desk. |
| Cancelled Vaccination with invoice history |  |  |  |  | Deferred | Requires vaccination record, Billing / Payment history, and normal cancellation through Desk. |
| Vaccination linked to consultation |  |  |  |  | Deferred | Requires creating vaccination from the consultation workflow. |
| Cancelled Hospitalisation with preserved history |  |  |  |  | Deferred | Requires hospitalisation with charge/activity history and normal cancellation through Desk. |
| Hospitalisation with stock/material issue reference |  |  |  |  | Deferred | Requires controlled hospitalisation stock/material issue workflow. |
| Cancelled Grooming Session with invoice history |  |  |  |  | Deferred | Requires grooming session, Billing / Payment history, and normal cancellation through Desk. |
| Cancelled Boarding Booking with invoice history |  |  |  |  | Deferred | Requires boarding booking, Billing / Payment history, and normal cancellation through Desk. |
| Boarding with charges |  |  |  |  | Deferred | Requires normal boarding charge workflow. |
| Completed Appointment linked to consultation |  |  |  |  | Deferred | Requires appointment check-in/start consultation and normal completion through Desk. |
| No-show Appointment preserving links/notes |  |  |  |  | Deferred | Requires appointment notes/reason and normal No Show action through Desk. |

#### Safety Confirmation

- Business data was not mutated outside normal Desk workflow.
- No records were created by script.
- No submitted Sales Invoice was edited, cancelled, amended, or repaired.
- No Payment Entry was edited or reallocated.
- No submitted Stock Entry or Stock Ledger Entry was edited.
- The read-only inventory was rerun and JSON was written to `/tmp` only.

#### Current Blockers / Defects

| ID | Area | Status | Description | Required Action |
|---|---|---|---|---|
| QA-10I-001 | Missing QA scenario preparation | Deferred | No live Desk session or role-user details were available in this agent session to prepare records manually. | QA staff should execute Phase 10G Desk preparation steps using actual role logins. |
| QA-10I-002 | Inventory readiness | Open | Missing scenario count remains 22. | Prepare or explicitly defer each scenario, then rerun inventory. |

#### Next Step

Run the Phase 10G Desk preparation checklist with real users on `vetedge.local` or staging, fill the QA record register with document names, rerun the read-only inventory, and update this section with the new found/missing counts.

- Completed consultation history preservation: `Completed` is a clinical closure/read-only state, not a history removal state. The consultation form keeps Billing / Payment, invoice history, appointment details, medical history, Latest Vitals, lab order history, vaccination history, and submitted dispensary Stock Entry links visible after completion. Latest Vitals is consultation-specific: it reads only `Veterinary Vital Signs` linked to the current consultation and no longer falls back to the patient's most recent vitals from another visit. New clinical mutation actions such as new lab orders, new vaccinations, new vitals, hospitalisation admission, and dispensary confirmation remain blocked or hidden where unsafe. Verification focuses on UI action visibility because backend completion validation only enforces gates/vitals and does not clear planned treatments, consultation invoice references, appointment links, clinical notes, lab/vaccination records, or submitted accounting/stock documents. Remaining risk: browser QA should still be used to verify any site-specific custom form layout or role permission hiding.
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
- Stock Expiry Monitor cloud build/runtime safety: the page no longer imports CoreEdge private EdgeUI Vue component source files at build time. The Desk page loader uses the public EdgeSuite runtime contract by loading `edgeui.bundle.js`, validating `window.EdgeUI.components`, then loading `vetedge_stock_expiry_monitor.bundle.js`; if the shared shell is missing, it shows an explicit failure block instead of raw unstyled success UI. App-local lightweight components remain available inside the VetEdge bundle so the product build does not require private CoreEdge frontend source paths.
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
