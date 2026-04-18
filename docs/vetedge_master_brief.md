# VetEdge Master Build Brief for Codex

## Purpose

This document defines the authoritative project scope and implementation rules for the VetEdge repository.

VetEdge is a veterinary operations system built as a custom Frappe/ERPNext app. It must be installable from GitHub in phase 1 and architected so that major modules can later be gated, limited, or licensed for SaaS and white-label deployments.

## Strategic direction

VetEdge is an independent veterinary domain app.

- It may borrow ideas or patterns from Marley where useful.
- It must not depend on Marley core doctypes or deep Marley overrides for its core workflows.
- ERPNext standard documents and infrastructure remain the source of truth for accounting, stock, payments, users, and permissions.

## Architecture summary

### VetEdge owns:
- veterinary patient domain
- consultation domain
- veterinary vitals
- appointments and queue
- treatment planning and dispensary linkage
- vaccination
- boarding
- owner portal and guest booking
- veterinary notifications
- veterinary dashboards and reports
- demo data management
- future feature gating shell

### ERPNext owns:
- Customer
- Item
- Sales Invoice
- Payment Entry
- stock and valuation logic
- warehouses
- users and roles
- companies and related core setup

## Locked business decisions

### 1. Consultation payment model
Support both operational modes:
- payment may be collected directly from consultation by doctor/front desk in small clinics
- payment may instead be routed to accounts before treatment

This must be controlled by settings and permissions.

### 2. Treatment stock posting
Treatment consumables are planned during consultation, but stock is deducted only on dispensary confirmation.

### 3. Vitals architecture
Use a separate `Veterinary Vital Signs` doctype.
The UI may allow vitals entry from the consultation page, but the data model remains independent.

### 4. Demo data deletion scope
Support seeded master data and demo transactions.
All demo data must be tagged by batch and removable safely by batch only.

### 5. Boarding vs inpatient
Boarding is phase 1.
Full inpatient hospitalization is deferred.

### 6. Diagnosis and symptoms structure
Use seeded master doctypes for diagnosis and symptoms, plus consultation child tables for transactional use.

## Major modules

### A. Settings and feature control
Create `Veterinary Settings` with tabbed sections for:
- General
- Consultation
- Billing
- Vitals
- Appointments
- Notifications
- Treatment & Inventory
- Boarding
- Portal
- Demo Data
- Security/Branch

Required feature flags include:
- enable_consultations
- enable_vitals
- enable_appointments
- enable_owner_portal
- enable_guest_booking
- enable_notifications
- enable_treatment_billing
- enable_dispensary_flow
- enable_vaccination
- enable_boarding
- enable_demo_tools
- enable_advanced_reports

### B. Licensing/profile shell
Create `VetEdge License Profile` as a future-ready shell for:
- plan_name
- subscription_status
- start_date
- expiry_date
- max_branches
- max_users
- enabled_modules
- white_label_enabled

No hard enforcement required in phase 1.

### C. Veterinary patient domain
Create VetEdge-owned doctypes for:
- Veterinary Patient
- Veterinary Species
- Veterinary Breed

`Veterinary Patient` should support core pet identity and owner linkage.

At minimum include:
- patient_name
- primary_owner (Customer)
- species
- breed
- sex
- neuter_status
- color_markings
- microchip_id
- date_of_birth
- approximate_age
- weight_baseline
- branch
- status
- emergency_contact
- is_deceased

### D. Consultation domain
Create `Veterinary Consultation` with:
- patient
- owner
- doctor
- branch
- status
- notes
- invoice reference
- payment status
- treatment plan summary

Related child tables:
- Consultation Symptom
- Consultation Diagnosis
- Planned Treatment Item

Recommended consultation statuses:
- Draft
- In Progress
- Awaiting Payment
- Ready for Treatment
- Completed
- Cancelled

### E. Veterinary vital signs
Create `Veterinary Vital Signs` with fields such as:
- patient
- consultation
- datetime
- temperature
- weight
- heart_rate
- respiratory_rate
- body_condition_score
- hydration_status
- mucous_membrane
- capillary_refill_time
- pain_score
- appetite_status
- notes

### F. Appointments and queue
Create `Veterinary Appointment` supporting:
- patient
- owner
- doctor
- branch
- appointment datetime
- status

Statuses:
- Scheduled
- Confirmed
- Checked In
- Completed
- Rescheduled
- Cancelled
- No Show

Requirements:
- appointments may be optional for consultation unless settings require them
- doctors can book next appointment during consultation
- create queue/dashboard views segmented into Today, Tomorrow, and Future

### G. Billing and payments
Use standard ERPNext billing.

Requirements:
- consultation may create or link a Sales Invoice
- consultation page may expose invoice/payment actions depending on settings and role permissions
- payment collection must use standard Payment Entry or approved ERPNext flow
- do not create parallel accounting behavior

### H. Treatment and dispensary
Model treatment planning separately from actual dispensing.

Recommended child structures:
- Planned Treatment Item
- Dispensed Treatment Item

Rules:
- planned items can exist before payment or dispensary action
- actual stock deduction happens only at dispensary confirmation
- bundled commercial billing may be supported, but inventory behavior must remain standard-safe

### I. Vaccination
Create VetEdge-owned vaccination doctypes:
- Veterinary Vaccine
- Veterinary Vaccination Record

Future extension may add schedules and reminders.

### J. Boarding
Create:
- Veterinary Boarding
- Veterinary Service Unit
- Veterinary Cage Room

Boarding should support:
- patient
- owner
- branch
- service unit / cage
- check-in
- check-out
- daily rate
- total days
- total charge
- status

Suggested statuses:
- Reserved
- Checked In
- In Stay
- Checked Out
- Cancelled

### K. Owner portal and guest booking
Portal must support two audiences:

#### Owner portal
Owners may:
- view pets
- view upcoming and past appointments
- reschedule or cancel where rules allow
- make payments
- view receipts
- view consultation summary/history only
- raise complaints/support issues

#### Guest booking
Guests may:
- request/book appointments
- provide pet and owner details
- choose preferred branch/date where enabled
- receive notifications

Do not expose sensitive internal consultation details, staff notes, or audit details in portal views.

### L. Notifications
Build a pluggable notification framework for:
- email
- SMS
- WhatsApp

Do not hardwire one provider.
Implement event-oriented routing for actions such as:
- appointment created
- appointment reminder
- appointment cancelled/rescheduled
- payment received
- complaint received

### M. Branch security
Create:
- Branch User Assignment
- Branch Practitioner Assignment

Rules:
- all sensitive access restrictions must be server-side
- client-side filters are not sufficient
- payment collection, dispensary confirmation, complaint resolution, and demo-data deletion must be role-aware and auditable

### N. Demo data
Create `Demo Data Batch`.

All demo records must carry:
- `is_demo_data`
- `demo_batch_id`

Support:
- master-data-only load
- full demo data load
- safe batch deletion with preview and explicit confirmation

## Required service layers

Create and prefer service modules such as:
- services/feature_flags.py
- services/licensing.py
- services/billing.py
- services/stock.py
- services/notifications.py
- services/branch_security.py
- services/portal_access.py
- services/consultation_flow.py
- services/appointment_flow.py
- services/demo_data.py
- services/boarding.py
- services/vaccination.py

Keep doctypes relatively thin. Put reusable business logic in services.

## Implementation constraints

Codex must:
- avoid modifying ERPNext core
- avoid modifying Marley core
- avoid large speculative scaffolding unless requested
- implement phase-by-phase
- keep naming consistent
- preserve ERPNext accounting and stock integrity
- use explicit validation
- keep critical logic server-side
- provide file-by-file summary after each task

## Preferred build order

1. repo foundations, settings, feature flags, role shell
2. veterinary patient and master doctypes
3. consultation and veterinary vitals
4. appointments, queue, guest booking, owner portal basics, notifications
5. billing/payment routing
6. dispensary and stock posting
7. boarding
8. vaccination
9. demo data tools
10. advanced reports and dashboards

## Required output from Codex for every phase

At the end of each phase, report:
1. files created
2. files modified
3. assumptions made
4. risks or open issues
5. recommended next phase
