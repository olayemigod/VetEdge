# VetEdge Clinical Inline Master Creation

## Goal

Allow clinical users to create missing Symptoms, Diagnoses, and Treatment Items without leaving active clinical workflows, while preserving the existing operational **Add Symptom**, **Add Diagnosis**, and **Add Treatment** row actions.

## UX Contract

1. The existing operational Add buttons remain unchanged.
2. Each row searches existing masters first.
3. When the typed value has no exact existing master and the relevant Veterinary Settings gate is enabled, the search results include a contextual **Create New ...** option.
4. Selecting that option opens a small creation dialog and, after successful creation, auto-selects the new master in the current row.
5. There are no new permanent **Add New Symptom / Add New Diagnosis / Add New Treatment Item** buttons.

## Veterinary Settings

All new settings default to disabled for backward compatibility:

- Allow New Symptoms in Clinical Workflow
- Allow New Diagnoses in Clinical Workflow
- Allow New Treatment Items in Clinical Workflow
- Allow Clinical Master Creation in Hospitalisation
- Allow ERPNext Item Creation from Treatment Item

Hospitalisation requires both the relevant master-creation setting and the Hospitalisation extension gate.

## Treatment Item and ERPNext Item Safety

Treatment Item creation searches existing ERPNext Items before offering ERPNext Item creation.

ERPNext Item creation additionally requires:

- the dedicated Veterinary Settings gate;
- an existing stock-capable role such as Stock User / Stock Manager / System Manager; and
- ERPNext create permission on Item.

The feature does not grant Item permissions by itself.

Treatment Item pricing resolves the contextual selling Price List in this order through the existing Billing Core:

1. Branch selling/VetEdge Price List;
2. Veterinary Settings default selling Price List;
3. ERPNext Selling Settings;
4. Standard Selling.

Users without pricing authority cannot override the resolved Price List or overwrite an existing Item Price at a different rate.

## Hospitalisation Boundary

Hospitalisation clinical medication/activity selection uses curated Veterinary Treatment Items and supports create-if-missing when enabled.

Hospitalisation charge editing deliberately retains the existing generic ERPNext Item search so existing charge-sheet workflows are not narrowed.

Diagnosis and Symptom storage are not duplicated onto Hospitalisation. The current Hospitalisation data model remains unchanged.

## Accounting / Stock Safety

This slice does not mutate submitted Sales Invoices, Payment Entries, Stock Entries, or other submitted accounting/stock documents.

Existing consultation treatment billing locks, source-generated row protections, Hospitalisation charge building, stock posting, and payment gates remain authoritative.

## Migration

No destructive data migration is required. A normal `bench migrate` adds the new Veterinary Settings fields. Defaults are off, so existing tenants retain current behaviour until explicitly enabled.

## Manual QA

### Consultation / EdgeSuite

- Add Symptom still adds a row.
- Search and select an existing Symptom.
- Search a missing Symptom with setting off: no Create New result.
- Enable setting and repeat: Create New appears.
- Create the Symptom and confirm it is auto-selected.
- Repeat for Diagnosis.
- Add Treatment still adds a treatment row.
- Search/select existing curated Treatment Item.
- Search missing Treatment Item with gate on and create it around an existing ERPNext Item.
- Confirm branch/default Price List resolution and resulting rate.
- With allowed Stock User + Item create permission, create a missing ERPNext Item from the Treatment dialog.
- Without Stock User or Item create permission, confirm ERPNext Item creation is unavailable.
- Confirm billed/source-generated treatment rows retain existing edit/remove locks.

### Native Consultation

- Symptom/Diagnosis Link quick-create is disabled when the respective gate is off.
- Enable the gate and confirm Frappe search/create becomes available for permitted users.
- Treatment search returns curated Treatment Items.
- Missing treatment returns VetEdge Create New Treatment Item, not generic direct Item creation.

### Hospitalisation

- Medication/Fluid Therapy clinical picker searches curated Treatment Items.
- Existing charge edit Item picker remains unchanged.
- With Hospitalisation extension off: no Treatment Item create result.
- Enable both Treatment Item and Hospitalisation gates: Create New Treatment Item appears.
- Create/select the new master and add the clinical activity.
- Confirm existing stock, charge, billing and invoice-sync safeguards remain unchanged.
