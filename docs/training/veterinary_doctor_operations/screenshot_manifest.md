# Screenshot Manifest

Screenshots were not captured during this documentation task because no safe authenticated local browser session or confirmed demo data was available. Capture these from the local development site only, preferably `vetedge.local`, using existing demo/test data.

| Screenshot filename | Page or route | Purpose | Role required | Data required | Capture instructions | Status |
|---|---|---|---|---|---|---|
| `doctor-dashboard-overview.png` | `/app/vetedge-clinical-dashboard` | Show the doctor’s clinical dashboard entry point | `VetEdge Doctor` | Any branch with clinical data preferred | Login as a doctor, open Clinical Dashboard, hide unrelated browser chrome, capture full visible page. | Pending |
| `appointment-queue-overview.png` | `/app/veterinary-appointment-queue` | Show appointment queue review | `VetEdge Doctor` | Existing appointment records | Open Appointment Queue with today filter if available, capture the queue list. | Pending |
| `patient-record-opened.png` | `/app/veterinary-patient/<patient>` | Show patient identity and owner area | `VetEdge Doctor` | Existing Veterinary Patient | Open a non-sensitive demo patient and capture top half of form. | Pending |
| `medical-history-timeline.png` | `/app/veterinary-medical-history` | Show patient medical history view | `VetEdge Doctor` | Patient with prior records | Open Medical History, select demo patient, capture timeline and filters. | Pending |
| `consultation-assessment-section.png` | `/app/veterinary-consultation/<consultation>` | Show complaint, assessment, diagnosis area | `VetEdge Doctor` | Existing consultation | Open a draft/in-progress consultation and capture Clinical Capture section. | Pending |
| `consultation-treatment-plan.png` | `/app/veterinary-consultation/<consultation>` | Show treatment plan and planned treatment rows | `VetEdge Doctor` | Existing consultation | Capture Treatment Plan section without changing data. | Pending |
| `billing-payment-modal.png` | Consultation or hospitalisation form | Show billing/payment modal behavior | `VetEdge Doctor` plus invoice access | Existing source with linked invoice | Click Billing / Payment only if safe; capture modal without submitting invoice or payment. | Pending |
| `lab-order-dialog.png` | Consultation form | Show new lab order picker/dialog | `VetEdge Doctor` | Saved consultation and active lab tests | Click New Lab Order; capture dialog; close without submitting unless on demo data. | Pending |
| `lab-order-summary.png` | `/app/veterinary-lab-order/<lab-order>` | Show lab order status and tests | `VetEdge Doctor` | Existing lab order | Open existing lab order and capture status and Lab Tests table. | Pending |
| `vaccination-entry.png` | `/app/veterinary-vaccination-record/<record>` | Show vaccination record fields | `VetEdge Doctor` | Existing vaccination record | Open existing vaccination record and capture top and clinical details. | Pending |
| `vaccination-dashboard.png` | `/app/vetedge-vaccination-dashboard` | Show due/overdue review surface | `VetEdge Doctor` | Existing vaccination records | Open dashboard and capture summary/cards if populated. | Pending |
| `hospitalisation-record-opened.png` | `/app/veterinary-hospitalisation/<record>` | Show admission and status fields | `VetEdge Doctor` | Existing hospitalisation | Open active hospitalisation and capture top admission/status fields. | Pending |
| `hospitalisation-activity-log.png` | Hospitalisation form, Activities tab | Show activity logging area | `VetEdge Doctor` | Active hospitalisation | Open Activities tab and capture activity table/buttons. | Pending |
| `discharge-readiness-checklist.png` | Hospitalisation form | Show discharge readiness dialog | `VetEdge Doctor` | Active hospitalisation | Click Check Discharge Readiness; capture dialog; do not discharge. | Pending |
| `veterinary-notification-badge.png` | Desk header or notification UI | Show Veterinary notification badge/feed | `VetEdge Doctor` | Existing notification item | Capture unread badge/feed; do not change status unless using demo data. | Pending |
| `doctor-reports-list.png` | Veterinary workspace sidebar or report list | Show doctor reports | `VetEdge Doctor` | None | Open Veterinary workspace/sidebar and capture Reports section. | Pending |

## Source files inspected

- `vetedge/workspace_sidebar/vetedge.json`
- `vetedge/veterinary/page/*/*.json`
- `vetedge/veterinary/doctype/*/*.json`
