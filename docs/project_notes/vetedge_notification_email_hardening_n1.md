# VetEdge Notification & Email Hardening N1

## Business Goal

Stop repeated or misleading VetEdge emails, make notification event ownership predictable, and ensure owner/staff emails use correct templates and settings without weakening existing SMS, in-app notification, accounting, or clinical workflows.

## Canonical Appointment Event Ownership

Veterinary Appointment lifecycle hooks own appointment lifecycle external notification emission.

- `after_insert` owns `appointment_created`.
- `on_update` owns status-transition events:
  - Scheduled → `appointment_scheduled`
  - Confirmed → `appointment_confirmed`
  - Checked In → `appointment_checked_in`
  - In Consultation → `appointment_started`
  - Completed → `appointment_completed`
  - Rescheduled → `appointment_rescheduled`
  - Cancelled → `appointment_cancelled`
  - No Show → `appointment_no_show`
- A genuine second reschedule while status already equals Rescheduled is detected from the appointment datetime change and emits exactly one new reschedule occurrence.
- Dedicated Checked In and Completed in-app notification items remain separate and idempotent.

Service flows must change/save the Appointment and must not re-emit the same lifecycle event.

## Duplicate Delivery Defence

Appointment lifecycle deliveries now use a stable per-occurrence idempotency key based on:

- event key
- reference DocType/name
- recipient
- channel
- previous/current status
- previous/current appointment datetime

`Veterinary Notification Log` now supports:

- unique `idempotency_key`
- temporary `Reserved` status
- 10-minute reservation window

Queued/Sent duplicates are suppressed. Failed, Skipped, or stale reservations can be retried.

This idempotency scope is deliberately limited to appointment lifecycle events. Reminder/batch events keep their existing occurrence mechanics.

## Portal / Guest Intake

One business request now produces one actionable staff intake event.

- Guest request with appointment requested → `guest_appointment_request_received`
- Guest registration without appointment request → `registration_request_received`
- Converted guest appointment awaiting approval → `guest_appointment_ready_for_approval`
- Owner portal appointment request → `owner_appointment_request_received`

Portal intake events are routed to branch-scoped:

- VetEdge Front Desk
- Branch Manager
- VetEdge Branch Manager
- VetEdge Administrator
- System Manager

The legacy `appointment_booked` alias is retained in the registry for backward compatibility but is no longer emitted immediately after an Appointment insert.

## Notification Settings

New settings default OFF:

- Notify on Payment Follow-up
- Notify on Clinical Workflow Updates

Corrected mappings include:

- payment initiated/pending/reminder → Payment Follow-up
- consultation sent to dispensary / ready for treatment / dispensary confirmation → Clinical Workflow Updates
- consultation/registration/grooming/boarding invoice + invoice PDF available → Invoice Created
- payment received + registration payment received → Payment Received

## Recipient Routing

Owner-facing routing is derived from the Notification Event Registry audience instead of a second manually maintained list.

`appointment_checked_in` remains supported and idempotent but is Internal Staff only.

Portal intake events use explicit branch-scoped front-desk/management routing.

## Email Template Mapping

Dedicated templates now exist for:

- Appointment Scheduled
- Appointment Checked In
- Appointment Started
- Appointment Completed
- Appointment No Show
- Invoice Created
- Payment Initiated
- Payment Reminder
- Consultation Awaiting Payment
- Registration Confirmed
- Grooming Appointment Confirmed
- Grooming Invoice Created
- Guest Appointment Request Received
- Guest Appointment Ready for Approval
- Owner Appointment Request Received
- Registration Request Received

All registry-mapped templates are present in the fixture.

Managed templates no longer contain the hard-coded `Powered by VetEdge` footer. Clinic branding remains primary.

Mixed Owner + Staff/Accounts templates use recipient-neutral wording.

## Template Render Failure

For events with a configured Email Template:

- missing template → Skip email and log diagnostic
- template render exception → Skip email and log diagnostic
- blank subject/body → Skip email and log diagnostic

VetEdge no longer silently sends a generic context dump when a configured template fails.

Unmapped/internal events may still use the privacy-filtered fallback. Fallback content excludes keys containing note, diagnosis, symptom, or medical markers.

## Upgrade / Migration

No destructive data migration is required.

A normal `bench migrate`:

1. adds the Notification Log idempotency field/status metadata;
2. adds the two Veterinary Settings fields;
3. runs VetEdge `after_migrate()`;
4. `setup_foundation()` calls `sync_vetedge_email_templates()`.

The template synchronizer updates VetEdge-managed templates and creates new templates while preserving templates that appear client-edited.

## Automated Regression Coverage

Relevant tests:

- `vetedge/services/test_notification_email_hardening.py`
- `vetedge/services/test_notifications.py`
- `vetedge/services/test_appointment_flow.py`
- existing appointment notification tests

Key contracts cover:

- one canonical lifecycle emitter
- no stale service-level appointment emitter
- repeated reschedule handling
- delivery key occurrence changes
- fail-closed template rendering
- registry-to-fixture template completeness
- white-label footer
- settings default OFF
- portal intake routing
- invoice/payment gate mappings

## Manual QA Before Merge

### Appointment Email Duplication

1. Enable Email notifications and appropriate appointment settings.
2. Create a normal appointment.
   - Confirm one Appointment Created email per intended recipient.
3. Confirm the appointment.
   - Confirm one Appointment Confirmed email.
4. Check in.
   - Confirm owner does not receive Checked In email.
   - Confirm connected internal recipient receives no duplicate external email.
   - Confirm in-app notification still appears.
5. Start consultation.
   - Confirm one Appointment Started email to intended internal recipient.
6. Complete appointment.
   - Confirm one Appointment Completed email per intended external recipient and in-app completion remains available.
7. Reschedule.
   - Confirm one Rescheduled email.
8. Reschedule the already-Rescheduled appointment to another datetime.
   - Confirm exactly one additional legitimate Rescheduled email.
9. Cancel and No Show flows.
   - Confirm one correctly worded email and no duplicate.

### Portal / Guest

1. Guest registration without appointment:
   - one Registration Request Received staff email.
2. Guest registration with appointment request:
   - one Guest Appointment Request Received staff email, not both registration + appointment emails.
3. Convert/approve guest appointment:
   - one Ready for Approval staff email where applicable.
4. Owner portal appointment request:
   - owner gets appointment acknowledgement;
   - branch front desk/management gets one Owner Appointment Request Received action email.

### Template Failures

1. Temporarily break a configured test template on a non-production test tenant.
2. Trigger its event.
3. Verify:
   - no generic replacement email is sent;
   - Notification Log records Skipped with render diagnostic.
4. Restore the template.

### Settings

Verify with each new setting OFF then ON:

- Payment Follow-up events
- Clinical Workflow Updates

Also confirm Invoice Created and Payment Received controls govern their registration/grooming/boarding variants.

### White Label

On a white-label tenant:

- email subject/body uses clinic name
- no managed email contains “Powered by VetEdge”
- client-edited template is not overwritten by migrate

## Safety Boundaries

This slice does not:

- mutate submitted invoices or payment documents
- alter accounting truth
- alter stock posting
- change the appointment SMS setting model
- remove appointment in-app notification idempotency
- force-overwrite client-edited email templates
- merge or deploy automatically
