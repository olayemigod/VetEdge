# VetEdge Role-Based Training Documentation Pack

This folder contains the role-based VetEdge training documentation pack. It supports onboarding, supervised practice, refresher training, client handover and Veterinary Training Centre display for every current VetEdge starter role bundle.

The same Markdown guides are available inside Desk through the Veterinary Training Centre page. Markdown remains the source of truth; the Desk page reads the module manifest and renders the approved guide files without copying them into database records.

Every operational user begins with:

- [Veterinary Home and EdgeSuite Daily Start](training-module:shared-veterinary-home)
- [Medical History Completion and Clinical Truth](training-module:shared-medical-history)
- [Safe Workflow Handoffs](training-module:shared-safe-handoffs)

Role learning paths include:

- [Veterinary Doctor Training Manual](training-module:doctor-overview)
- [Owner and Administrator Operations](training-module:owner-administrator-operations)
- [Branch Manager Operations](training-module:branch-manager-operations)
- [Veterinary Nursing Operations](training-module:nursing-operations)
- [Front Desk Operations and Billing Center](training-module:front-desk-operations)
- [Accounts, Cashier and Billing Operations](training-module:accounts-billing-operations)
- [Dispensary and Stock Operations](training-module:dispensary-stock-operations)
- [Laboratory Operations](training-module:laboratory-operations)
- [Grooming Operations](training-module:grooming-operations)
- [Boarding Operations](training-module:boarding-operations)

Use the module guides when a trainer or doctor needs more detail for a specific workflow:

- [Role Access Matrix](training-module:role-access)
- [Doctor Daily Workflow](training-module:daily-workflow)
- [Patient Medical Record Workflow](training-module:patient-record)
- [Veterinary Masters Awareness Reference](training-module:veterinary-masters)
- [Consultation Workflow](training-module:consultation)
- [Lab Order Workflow](training-module:lab-order)
- [Vaccination and Preventive Care Workflow](training-module:vaccination)
- [Hospitalisation Workflow](training-module:hospitalisation)
- [Grooming Service Handoff Workflow](training-module:grooming-handoff)
- [Boarding Service Handoff Workflow](training-module:boarding-handoff)
- [Notifications and Action Centre Workflow](training-module:notifications)
- [Reports and Dashboards Workflow](training-module:reports-dashboards)
- [Troubleshooting and Common Errors](training-module:troubleshooting)
- [Glossary](training-module:glossary)
- [Screenshot Manifest](training-module:screenshot-manifest)
- [Training Module Manifest](training_modules.json)
- Training Centre Manual QA Checklist: `training_centre_manual_qa_checklist.md`

## How to Use This Pack

1. Complete the three Shared Operations modules.
2. Open the learning path visible for the trainee's assigned role bundle.
3. Use the practical exercises during supervised practice.
4. Use the checklist and assessment sections before allowing independent production use.
5. Use the screenshot manifest to track which images are captured or still pending.
6. In Desk, open `Training Centre` from the Veterinary workspace/sidebar to read the same modules.
7. Use the manual QA checklist before handing the Training Centre to clinic trainers or users.

## Desk Training Centre

- Desk page: `Veterinary Training Centre`
- Workspace label: `Training Centre`
- User-facing location: `Veterinary` -> standalone `Training Centre` sidebar section
- Standard Frappe route: `/app/veterinary-training-centre`
- Module deep-link format: `/app/veterinary-training-centre?module=<module_id>`
- Module source: [training_modules.json](training_modules.json)
- Guide source: Markdown files in this folder
- Video source: optional `youtube_url` per module in [training_modules.json](training_modules.json)
- Manual QA checklist: `training_centre_manual_qa_checklist.md`

Markdown remains the source of truth for training guide content. The Desk page reads the approved module list and renders the Markdown guide files; it does not copy the manuals into database records.

Related-guide links inside the Training Centre open Desk training modules, not raw Markdown files. Use `training-module:<module_id>` links in Markdown when adding new internal training references.

For now, videos are placeholders. Add YouTube videos later module by module by updating the `youtube_url`, `video_title`, and `video_status` fields in [training_modules.json](training_modules.json). Use only approved YouTube links. Screenshots remain pending until manually captured and reviewed.

Mermaid workflow blocks are rendered visually inside the Training Centre using the local Mermaid bundle at `/assets/vetedge/js/lib/mermaid.min.js`. The bundled asset comes from the official `mermaid` npm package and is tracked with its source and license notes in `vetedge/public/js/lib/`. If Mermaid is unavailable or a diagram cannot be rendered, the Training Centre falls back to its simple safe flowchart renderer where possible. Invalid diagrams keep their source visible with a friendly note instead of breaking the guide.

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

Screenshots are currently placeholders. See [screenshot_manifest.md](training-module:screenshot-manifest) for filename, route, purpose, role required, capture instructions, and status.

## Folder Scope

The Markdown files are documentation only. The Training Centre service enforces role visibility from the module role group; it does not grant DocType, report, page, branch, stock or accounting permission.
