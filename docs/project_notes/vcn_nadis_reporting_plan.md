# VCN / NADIS Regulatory Reporting Plan

## Business goal

Allow veterinary practices using VetEdge to prepare Veterinary Council / NADIS regulatory submissions from operational data already captured during normal clinic work, with minimal duplicate entry and without creating a separate reporting architecture.

The authoritative source workbooks previously supplied are:

- `Nadis Template Vaccination Report 1.xlsx`
- `NadisTemplate Disease Outbreak Report.xlsx`

Exact workbook headers, merged cells, prescribed labels, ordering and submission formatting must be verified against those source files before a generated workbook is described as submission-ready.

## Product layer

- VetEdge owns veterinary source data, regulatory mappings and report-specific validation.
- EdgeSuite UI provides the shared report shell and export interaction.
- CoreEdge may later provide scheduled delivery/usage/notification services, but regulatory data truth remains in VetEdge.

## Phase 7A — Regulatory source adapters

### NADIS Vaccination Source

Status: implemented.

Source objects:

- `Veterinary Vaccination Record`
- `Veterinary Patient`
- `Customer`
- `Veterinary Vaccine`
- `Branch`
- `Company`
- `User`

Implemented source fields include vaccination record, administered date/time, Branch, Company, patient, patient name, owner, species, breed, vaccine, dose, route, batch number, batch expiry date, administering practitioner, status and next due date.

The source endpoint is query-paginated and reuses the established `Vaccination Report` role/Branch visibility contract. It is deliberately marked:

- `template_mapping_verified = false`
- `submission_ready = false`

until the authoritative spreadsheet is re-opened and mapped field-by-field.

### Disease surveillance / outbreak source

Status: audit complete; official source object not yet implemented.

VetEdge currently records diagnoses through `Consultation Diagnosis` linked to `Veterinary Diagnosis` and `Veterinary Consultation`. This is sufficient for clinical diagnosis history and could support an internal disease-occurrence surveillance view.

It is **not sufficient to represent an official outbreak event** because the current model does not provide a dedicated regulatory event with confirmed outbreak geography, affected population/exposure denominator, number of cases, deaths, animals at risk, outbreak start/end, investigation/confirmation state, control measures, reporting authority/reference, or other template-specific epidemiological fields.

Therefore the NADIS Disease Outbreak Report must not infer or manufacture an outbreak solely because one or more consultations contain a diagnosis.

## Phase 7B — Authoritative template mapping

When the two source workbooks are available again:

1. Record every worksheet name, exact column label, heading/merged-cell structure, required/optional field, accepted value format and totals/signature area.
2. Map each Vaccination template field to the Phase 7A source dataset.
3. Classify each Disease Outbreak field as:
   - already captured in VetEdge;
   - derivable safely from existing records;
   - requires explicit outbreak capture;
   - clinic/facility setting;
   - regulatory/export-only constant.
4. Do not add a field to an operational DocType merely because it appears in an export template unless it genuinely belongs to that business object.
5. Save the mapping as a documented, tested contract before implementing spreadsheet generation.

## Phase 7C — Disease outbreak capture

If template verification confirms the expected gap, introduce a small dedicated regulatory DocType, provisionally `Veterinary Disease Outbreak`, rather than overloading `Veterinary Consultation`.

The final fields must be driven by the NADIS template. Likely relationships—not final field definitions—include:

- reporting Branch / Company;
- diagnosis/disease;
- species and affected population context;
- geographical/location context;
- first observed / report / resolution dates;
- case/death/at-risk counts where required;
- linked consultations/patients or supporting clinical records;
- investigation/confirmation/reporting state;
- control/action notes;
- regulator reference/submission status.

No provisional field above should be treated as an approved schema until the workbook mapping is complete.

## Phase 7D — Regulatory report UI

Expose verified reports through the shared `EdgeReportShell` / Report Center standard.

Requirements:

- regulatory reports are Standard-plan operational/compliance reports;
- date, Branch, Company and workflow-relevant smart filters;
- server-authoritative Branch/role/DocType permission checks;
- paginated interactive data;
- clickable source records where appropriate;
- visible validation state such as Ready / Missing Required Data / Template Mapping Pending;
- no large hidden master loads.

## Phase 7E — Official workbook export presets

Create dedicated NADIS export presets only after template mapping is verified.

The export path must:

- preserve required worksheet names and layout;
- populate exact expected columns/cells;
- preserve required headings and merged sections where applicable;
- use correct date/number formats;
- calculate required totals explicitly;
- identify missing mandatory data before file generation;
- reopen/validate the produced workbook in automated tests;
- never claim submission readiness when required source fields are unavailable.

This official-template path should be separate from ordinary generic XLSX/CSV/PDF exports so future changes to EdgeSuite presentation exports cannot silently alter the regulatory workbook format.

## Safety and compatibility

- All regulatory source/report endpoints are read-only.
- Do not mutate submitted Sales Invoices, Payment Entries, Stock Entries or other submitted accounting/stock documents.
- Do not infer an outbreak from diagnoses without an explicit approved outbreak model/rule.
- Preserve existing Vaccination and Consultation workflows.
- Use idempotent patches if new regulatory schema is later introduced.
- Keep Branch/company/role access server-authoritative.
- Regulatory reporting remains available as a Standard compliance capability; Advanced Reporting entitlement should not be required for mandatory reports.

## Tests required

### Automated

- Branch-scoped zero-assignment fail closed.
- Cross-Branch report/source access denied.
- Vaccination source pagination and 100-row maximum page.
- Patient/species/breed enrichment only for visible source rows.
- Owner/customer filter alias parity.
- Read-only/no-mutation contract.
- Exact official workbook mapping tests once templates are available.
- Generated workbook reopen/integrity tests once official export is implemented.

### Manual browser/file QA

- Date/Branch/Company filters.
- Practitioner/Vaccine/Species filtering after UI exposure.
- Multi-branch user switching.
- Standard-plan visibility.
- Pagination and low-data network behavior.
- Official workbook comparison cell-by-cell against the supplied template after Phase 7B.

## Current blockers / dependencies

The exact NADIS source workbooks are not currently retrievable from File Library in this session, and reliable public copies were not found during the current verification pass. Phase 7A can proceed from existing VetEdge source truth; Phase 7B official template mapping remains blocked until the authoritative files can be opened again.
