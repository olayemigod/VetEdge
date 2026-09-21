# Medical History Completion and Clinical Truth

## Module Purpose

Understand exactly when consultation, vitals, laboratory, vaccination, hospitalisation and billing activity becomes visible in patient-centred Medical History.

## Core Rule

Medical History presents clinical truth from saved source records. Workflow status—not a manually described outcome—controls whether laboratory and vaccination activity is included.

| Source | When it appears | What remains excluded |
|---|---|---|
| Consultation | Saved patient-linked encounter content, including symptoms, diagnosis and planned treatment | Unlinked or wrong-patient records; final-status rules still govern later clinical orders |
| Veterinary Vital Signs | Saved structured observations and trend charts | Vitals written only in free-text notes do not create a structured vitals record |
| Veterinary Lab Order | Only when workflow status is `Completed` | Draft, Ordered, Sample Collected, Sent to Lab, In Progress, Result Entered, Reviewed and incomplete work |
| Veterinary Vaccination Record | Only when workflow status is `Administered` | Draft, Awaiting Payment and Pending Administration work |
| Hospitalisation | Admission, non-duplicated inpatient activity and discharge events | Linked lab, vaccination and vitals records are not repeated as free-text hospital activity |
| Billing | Billing does not create clinical history | A payment gate may delay the clinical completion or administration action that creates history |

Frappe document status and VetEdge workflow status are separate controls. Submitting or saving a record does not make an unfinished laboratory order `Completed` or a pending vaccination `Administered`.

## Step-by-Step Verification

1. Open the correct Veterinary Patient and confirm patient ID and Primary Owner.
2. Open **Medical History** at `/app/veterinary-medical-history`.
3. Review the timeline using the required date and record filters.
4. If an expected laboratory event is missing, open the Lab Order and read its workflow status. Do not mark it Completed until result entry, review and clinical work are genuinely complete.
5. If a vaccination is missing, open the Vaccination Record and read its workflow status. Do not use `Administered` before the vaccine is actually given and required checks pass.
6. If structured vitals are missing, confirm a Veterinary Vital Signs record was saved for the patient.
7. If a hospitalisation event is missing, confirm the episode and relevant activity or discharge action were saved against the correct patient.
8. If billing is blocking a clinical action, hand the invoice or payment exception to the authorised finance role. Never fabricate a clinical status to make history appear.

## Practice Exercise

Using trainer-approved synthetic records, compare one unfinished Lab Order, one completed Lab Order, one pending vaccination and one administered vaccination in Medical History. Explain why only the completed clinical truth appears.

## Completion Check

- [ ] Patient identity confirmed.
- [ ] Structured vitals kept separate from consultation text.
- [ ] Lab included only at Completed.
- [ ] Vaccination included only at Administered.
- [ ] Billing understood as a gate, not a clinical history event.

## Related Screenshots

![Medical History completed clinical timeline](training_assets/screenshots/medical-history-completion-rule.png)
