# AGENTS.md

## Project identity

- App name: `vetedge`
- Module label: `Veterinary`
- Company/brand: `ProcessEdge Solutions`
- Stack: Frappe / ERPNext custom app
- Phase target: GitHub-installable app first, future SaaS-ready architecture later

## Product intent

VetEdge is an independent veterinary domain app.
It is **inspired by Marley patterns where useful**, but it must **not depend on Marley core doctypes or deep Marley overrides for its core business logic**.

ERPNext standard infrastructure must be used for:
- accounting
- invoicing
- payment entry
- stock/inventory
- users
- permissions
- branches/companies where applicable

VetEdge owns veterinary workflows and veterinary data models.

## Non-negotiable architecture rules

1. Do **not** modify ERPNext core.
2. Do **not** modify Marley core.
3. Do **not** model the app as a fragile overlay on Marley.
4. Prefer **new VetEdge-owned doctypes** over patching unrelated healthcare doctypes.
5. Keep veterinary domain logic inside VetEdge services and doctypes.
6. Use ERPNext standard accounting and stock flows; do not invent parallel posting logic.
7. Every major feature must be modular and future feature-gatable for SaaS/subscription use.
8. All permission-sensitive logic must be enforced server-side.

## Core design principle

Build VetEdge as a deployable single-tenant app now, but architect each major module so it can later be:
- enabled or disabled by plan
- limited by subscription/license rules
- used in white-label deployments
- used in future SaaS hosting

Do **not** build full subscription enforcement now unless explicitly requested.
Do build:
- feature flags
- modular services
- license/profile shell
- clean boundaries between modules

## Primary modules

The app should be structured around these domains:

- Settings & Feature Control
- Licensing/Profile Shell
- Veterinary Patient
- Consultation
- Veterinary Vital Signs
- Appointments
- Consultation Billing & Payment Routing
- Treatment & Dispensary
- Vaccination
- Boarding
- Owner Portal
- Guest Booking
- Notifications
- Branch Security
- Demo Data
- Reports & Dashboards

## Current business decisions already locked

### Consultation payment model
Support both flows:
- small clinics may allow doctor/front desk to collect payment directly from consultation
- other clinics may route payment to accounts before treatment

This must be settings-driven and role-controlled.

### Treatment stock posting
Do **not** deduct stock at consultation planning time.
Deduct stock only on **dispensary confirmation**.

### Vitals architecture
Use a **separate VetEdge doctype** for vitals.
Vitals may be entered from the consultation page, but the data model remains separate.

### Demo data
Support:
- seeded master data
- demo transactions
Both must be tagged by batch and removable safely by batch only.

### Boarding vs inpatient
Implement **boarding first**.
Do not implement full inpatient hospitalization unless asked in a later phase.

### Diagnosis and symptoms model
Use:
- seeded master doctypes for diagnosis and symptoms
- child tables inside consultations for transactional capture

## Repo conventions

### Suggested top-level layout
- `vetedge/veterinary/doctype/` for VetEdge doctypes
- `vetedge/services/` for orchestration/business logic
- `vetedge/api/` for whitelisted/server endpoints
- `vetedge/portal/` for owner/guest portal logic
- `vetedge/notifications/` for channel/event routing
- `vetedge/reports/` for reports
- `vetedge/dashboard/` for workspaces/chart sources
- `vetedge/seed/` for install seed data and demo files
- `vetedge/install/` for setup/install hooks
- `docs/` for build docs and architecture notes

### Implementation preference
Prefer:
- thin doctypes
- reusable service functions
- explicit validation
- settings/feature checks
- idempotent setup scripts
- clean file names that match doctypes

Avoid:
- fat client scripts driving critical logic
- hidden business rules in JS only
- deep monkey patches
- unrelated workspace clutter
- duplicate billing or stock logic

## Expected core doctypes

Minimum domain doctypes likely include:
- Veterinary Settings
- VetEdge License Profile
- Veterinary Species
- Veterinary Breed
- Veterinary Symptom
- Veterinary Diagnosis
- Veterinary Service Type
- Veterinary Treatment Type
- Veterinary Vaccine
- Veterinary Patient
- Veterinary Consultation
- Consultation Symptom
- Consultation Diagnosis
- Planned Treatment Item
- Dispensed Treatment Item
- Veterinary Vital Signs
- Veterinary Appointment
- Veterinary Vaccination Record
- Veterinary Boarding
- Veterinary Service Unit
- Veterinary Cage Room
- Owner Complaint
- Demo Data Batch
- Branch User Assignment
- Branch Practitioner Assignment

Do not create all doctypes blindly in one task unless explicitly asked.
Implement only what is needed for the current phase.

## ERPNext integration rules

### Billing
Must use standard ERPNext:
- Sales Invoice
- Payment Entry

Consultation should create or link invoice records and use standard payment flow.
Never bypass ERPNext accounting integrity.

### Inventory
Must use standard ERPNext item and stock behavior.
Treatment consumables may be planned in consultation, but stock posting occurs only on dispensary confirmation.

### Customers / owners
Pet owners should be linked to ERPNext `Customer` records for commercial/billing integrity.

## Portal rules

There are two portal audiences:
- authenticated owners
- guest/new clients

### Owner portal scope
Owners may:
- view pets
- book appointments
- view and manage appointments where allowed
- make payments
- view receipts
- view consultation summary/history without exposing sensitive internal clinical details
- raise complaints/support requests

### Guest portal scope
Guests may:
- request/book appointments
- submit pet and owner details
- receive confirmation notifications

Do not expose internal-only consultation details, staff notes, audit trails, or dispensary internals in the portal.

## Notification rules

Notification channels should be abstracted:
- email
- SMS
- WhatsApp

Do not hardwire a single vendor.
Use a service layer that can route by channel and event.

Settings should support event toggles and future pluggable providers.

## Branch and security rules

- Branch-sensitive access must be validated server-side.
- Client-side filters are convenience only, never the real security model.
- Payment actions, demo-data deletion, dispensary confirmation, and portal access must be role-validated and auditable.
- Design all critical actions with future auditability in mind.

## Demo data rules

All demo data must be tagged with:
- `is_demo_data`
- `demo_batch_id`

Deletion must:
- preview affected counts
- remove only tagged records
- never remove client-created real data
- require explicit confirmation

## SaaS-readiness rules

Design all major modules so they can later be controlled by:
- feature flags
- plan/license checks
- enabled module lists
- max users/max branches rules

For now, create structure and service hooks for this.
Do not overbuild enforcement until requested.

## Testing and verification

For each implementation phase:
- add or update focused tests where practical
- verify model validation
- verify service behavior
- verify branch/security logic for sensitive actions
- keep tests targeted, not sprawling

When finishing a task, always report:
1. files created
2. files modified
3. assumptions made
4. risks or open issues
5. suggested next phase

## Codex work mode

Always work phase-by-phase.

Before coding:
- inspect the current repo
- read this `AGENTS.md`
- read relevant docs under `docs/`
- propose or follow the requested phase only

Unless explicitly asked, do not:
- scaffold the whole product at once
- add speculative modules
- refactor unrelated code
- change naming conventions already decided

## Priority implementation order

Preferred build order:
1. settings / feature flags / repo foundations
2. patient + owners + masters
3. consultation + vitals + child tables
4. appointments + queue + portal booking + notifications
5. billing + payment flow
6. dispensary + stock posting
7. boarding
8. vaccination
9. demo data tools
10. advanced dashboards and reports

## Done means

A phase is considered done only when:
- the requested scope is implemented
- files are placed in the agreed repo structure
- validations exist
- major assumptions are documented
- code does not break ERPNext accounting/inventory rules
- output summary is provided
