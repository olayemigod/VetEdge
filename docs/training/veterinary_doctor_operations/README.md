# Veterinary Doctor Training Documentation Pack

This folder contains the doctor-facing VetEdge training documentation pack. It is written for practical clinic use: onboarding new veterinary doctors, running live staff training, supporting client handover, displaying content in a future Training Centre, and preparing for future PDF export.

The same Markdown guides are available inside Desk through the Veterinary Training Centre page. Markdown remains the source of truth; the Desk page reads the module manifest and renders the approved guide files without copying them into database records.

Start with the main manual:

- [Veterinary Doctor Training Manual](veterinary_doctor_training_manual.md)

Use the module guides when a trainer or doctor needs more detail for a specific workflow:

- [Role Access Matrix](role_access_matrix.md)
- [Doctor Daily Workflow](doctor_daily_workflow.md)
- [Patient Medical Record Workflow](patient_medical_record_workflow.md)
- [Veterinary Masters Awareness Reference](veterinary_masters_reference.md)
- [Consultation Workflow](consultation_workflow.md)
- [Lab Order Workflow](lab_order_workflow.md)
- [Vaccination and Preventive Care Workflow](vaccination_and_preventive_care_workflow.md)
- [Hospitalisation Workflow](hospitalisation_workflow.md)
- [Grooming Service Handoff Workflow](grooming_workflow.md)
- [Boarding Service Handoff Workflow](boarding_workflow.md)
- [Notifications and Action Centre Workflow](notifications_and_action_centre_workflow.md)
- [Reports and Dashboards Workflow](reports_and_dashboards_workflow.md)
- [Troubleshooting and Common Errors](troubleshooting_and_common_errors.md)
- [Glossary](glossary.md)
- [Screenshot Manifest](screenshot_manifest.md)
- [Training Module Manifest](training_modules.json)

## How to Use This Pack

1. Open the main training manual and use it as the live training agenda.
2. Open each module guide when trainees need a deeper walkthrough.
3. Use the practical exercises during supervised practice.
4. Use the checklist and assessment sections before allowing independent doctor use.
5. Use the screenshot manifest to track which images are captured or still pending.
6. In Desk, open `Training Centre` from the Veterinary workspace/sidebar to read the same modules.

## Desk Training Centre

- Desk page: `Veterinary Training Centre`
- Workspace label: `Training Centre`
- Module source: [training_modules.json](training_modules.json)
- Guide source: Markdown files in this folder
- Video source: optional `youtube_url` per module in `training_modules.json`

For now, videos are placeholders. Add a YouTube URL later in the manifest when a module video is ready. Screenshots remain pending until manually captured and reviewed.

## Training Safety Rules

- Use existing safe demo or training records where available.
- Do not create duplicate patient records during training.
- Do not manually alter submitted invoices.
- Do not bypass payment, permission, branch, or stock messages.
- Treat grooming and boarding as non-clinical service workflows unless the clinic explicitly grants additional role access.
- If billing or payment blocks a workflow, involve Front Desk or Accounts.
- If stock or warehouse messages appear, involve Pharmacy, Dispensary, or the stock team.
- If access differs on the live site, verify the user's roles in Role Permission Manager.

## Screenshot Status

Screenshots are currently placeholders. See [screenshot_manifest.md](screenshot_manifest.md) for filename, route, purpose, role required, capture instructions, and status.

## Folder Scope

This folder is documentation only. It does not change DocTypes, permissions, business logic, reports, dashboards, fixtures, patches, hooks, migrations, or live data.
