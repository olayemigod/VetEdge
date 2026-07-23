# VetEdge Full EdgeSuite Document Migration

## Purpose

Migrate VetEdge operational documents from native Frappe Desk screens into the full EdgeSuite UI experience while preserving VetEdge business logic, Frappe permissions, workflow controls, tenant and branch isolation, and ERPNext accounting truth.

This plan replaces the rejected CSS-only adaptation approach. A document is considered migrated only when its list, create/edit form, dependent fields, child tables, workflow actions, dialogs, permissions, responsive layout, and business-specific actions work inside an EdgeSuite application page.

## Architecture

### Shared EdgeSuite UI layer

EdgeSuite UI 0.5 provides product-neutral components:

- `EdgeDataTable`
- `EdgeDocumentForm`
- `EdgeChildTable`
- `EdgeWorkflowBar`
- `EdgeSettingsLayout`
- Existing EdgeSuite shell, filters, links, statuses, loading/error/empty states, and modals

The shared library does not call product write APIs. Each product remains responsible for permissions, validation, workflow transitions, and business actions.

### VetEdge provider layer

`vetedge.services.document_workspace` provides an explicit resource allowlist and:

- Permission-aware list queries
- Branch filters and defaults
- Frappe metadata-to-EdgeSuite form schemas
- Normal document insert/save/delete behaviour
- Standard Workflow transitions
- Context-aware Link queries
- Product-specific action providers
- Platform access enforcement
- Optimistic timestamp protection

Complex clinical and accounting workflows must receive dedicated providers. They must not be enabled through a generic metadata form alone.

## Phase 1: Foundation and low-risk operational documents

Status: Implemented on `agent/vetedge-full-edgeui-documents-phase1`.

### Veterinary Patient

- EdgeSuite list and filters
- Add Patient
- Full tabbed form
- Owner, species, breed, and branch links
- Species-to-breed filtering
- Child tables
- Save and safe draft deletion
- New Appointment action

### Veterinary Appointment

- EdgeSuite list and filters
- Add Appointment
- Full tabbed form
- Patient filtering excludes deceased patients
- Practitioner lookup uses valid Veterinary doctors only
- Branch defaults and filtering
- Approve, confirm, check-in, cancel-request, and start-consultation actions
- Related registration and consultation links

### Veterinary Settings

- Full grouped EdgeSuite Settings layout
- Every source-controlled tab and section
- Field dependencies and mandatory/read-only conditions
- Child tables
- Password values protected from browser disclosure and accidental blank overwrite
- Normal Single DocType save and validation

## Remaining phases

### Phase 2: Front Desk and supporting masters

- Veterinary Missed Appointment and action centre conflict resolution
- Customer-facing registration requests
- Consultation Type and relevant operational masters
- Care locations, kennels, species, breeds, and treatment masters

### Phase 3: Consultation

Requires dedicated providers for:

- Consultation status lifecycle
- Vitals and clinical sections
- Planned treatment rows
- Laboratory and vaccination ordering
- Ready for Treatment lock
- Billing sessions and invoice history
- Payment gates
- Follow-up creation
- Medical history

Submitted accounting documents must never be mutated.

### Phase 4: Laboratory and Vaccination

- Laboratory orders, test rows, result capture/review, uploads, billing, and replacement-invoice safety
- Vaccination records, stock context, next-due scheduling, notification controls, and billing

### Phase 5: Hospitalisation

- Admissions, care activities, care locations, occupancy, daily charges, charge synchronisation, discharge readiness, and discharge workflow

### Phase 6: Grooming and Boarding

- Booking, check-in/admission, service delivery, care logs, billing, completion/discharge, and occupancy views

### Phase 7: Reports, dashboards, and administrative utilities

- Continue migrating remaining reports and utility pages to shared EdgeSuite layouts
- Integrate VCN/NADIS reports
- Replace temporary Resource Center routes once every corresponding full workflow is accepted

## Migration safety rules

- Preserve existing DocType names, module identity, routes, controllers, and hooks unless a separate migration is approved.
- Keep all server-side validation and permission checks.
- Use allowlisted resources; never expose arbitrary DocTypes through a generic API.
- Apply branch and company context on both frontend and backend.
- Clear invalid dependent Link values when parent context changes.
- Do not mutate submitted Sales Invoices, Payment Entries, Stock Entries, or other submitted accounting documents.
- Do not replace dedicated VetEdge service APIs with direct browser database writes.
- Keep legacy screens available until each replacement passes automated and manual QA.

## Phase 1 QA checklist

### Patient

- List/search/filter by branch, status, species, breed, and owner
- Create and update a patient
- Species change restricts Breed choices
- Invalid or deceased state rules remain enforced
- Permissions differ correctly for Front Desk, Doctor, Nurse, Branch Manager, and Administrator
- New Appointment opens with Patient prefilled

### Appointment

- List/search/filter by status, branch, doctor, type, and patient
- Create and update an appointment
- Doctor field lists only valid Veterinary doctors
- Patient field excludes deceased patients
- Approve, confirm, check-in, cancel request, and start consultation
- Existing linked consultation opens safely
- Branch integrity remains enforced

### Settings

- Every settings group loads
- Dependencies show/hide and require fields correctly
- Child-table add/edit/remove works
- Existing password values are not displayed
- Blank password fields do not clear stored credentials
- Save runs Veterinary Settings validation

### Responsive and accessibility

- Desktop, tablet, and mobile widths
- Keyboard row opening and action buttons
- Modal focus and close behaviour
- Long labels and values do not overflow
- Empty, loading, and error states are clear
