# Front Desk Operations and Billing Center

## Module Purpose

Register owners and patients, manage bookings and appointments, coordinate check-in, maintain accurate queues and provide controlled billing visibility without editing clinical or submitted accounting records.

## Start of Day

1. Open Veterinary Home and confirm branch and date.
2. Open Appointment Queue at `/desk/vetedge-front-desk-queue`.
3. Review Guest Booking Requests, missed appointments, boarding bookings and the day's appointment workload.
4. Confirm owner contact details and search for the patient by name, owner, species and microchip before creating a new record.

## Appointment Workflow

1. Review an Owner Requested appointment and select the approved action.
2. Confirm a Scheduled appointment when the clinic has accepted the slot.
3. Check In only when the patient has arrived and identity is confirmed.
4. Start Consultation or hand off to the practitioner only from the valid current state.
5. Use Rescheduled, Cancelled or No Show accurately; do not leave abandoned appointments in an active status.
6. Record missed-appointment follow-up from its source record and close the work item only after action.

## Billing Center

1. Open `/desk/vetedge-billing-center`.
2. Confirm Company and Branch. For restricted users, only assigned branch data should be available.
3. Review open Billing Sessions, outstanding sessions, outstanding amount and amount collected.
4. Filter Customer before Patient to avoid a wrong-owner billing review.
5. Open the authoritative Billing Session and latest Sales Invoice.
6. Send invoice submission, payment allocation, refund, credit or submitted-document correction to Accounts/Cashier.
7. Refresh Billing Center after the authorised financial action.

## Clinical Boundary

Front Desk may coordinate registration, appointments, owners and service handoffs. Front Desk must not enter a diagnosis, falsify consultation completion, mark laboratory work Completed, mark a vaccination Administered or overwrite practitioner documentation.

## Practice Exercise

Process a synthetic Owner Requested appointment through confirmation and check-in, open the linked patient, inspect Billing Center and prepare a complete practitioner or finance handoff without altering clinical or submitted accounting data.

## Related Screenshots

![Front Desk Appointment Queue](training_assets/screenshots/front-desk-appointment-queue.png)
![Billing Center filters and sessions](training_assets/screenshots/billing-center.png)
