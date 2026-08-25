# VCN / NADIS Regulatory Reporting Implementation

## Business goal

Allow veterinary practices using VetEdge to prepare Veterinary Council / NADIS regulatory submissions from operational data already captured during normal clinic work, with minimal duplicate entry and without creating a separate reporting architecture.

## Authoritative workbooks

The two workbooks supplied directly for implementation have now been inspected and mapped:

- `Nadis Template Vaccination Report 1.xlsx`
  - SHA-256: `458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba`
  - official sheet: `Vaccinations`
  - visible title: `Monthly Vaccination Report`
  - data begins on row 5.
- `NadisTemplate Disease Outbreak Report.xlsx`
  - SHA-256: `8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94`
  - official sheets: `Outbreaks`, `Animals affected`, `Bases of Diagnosis`, `Disease Control Measures`, `Locations`
  - data begins on row 5.

Exact visible headings, field-ID rows, sheet names, date hints and controlled values are captured in `vetedge/services/nadis_templates.py`. The original binary workbooks remain the acceptance reference for final Excel QA.

## Product layer

- VetEdge owns veterinary source data, regulatory mappings, validation and official workbook generation.
- EdgeSuite UI owns the Regulatory Reporting workbench.
- CoreEdge may later provide scheduled delivery, notification and platform governance services, but regulatory data truth remains in VetEdge.
- Regulatory reports are Standard-plan compliance capability; they do not require Advanced Reporting entitlement.

## Phase 7A — Regulatory source adapter

Status: **implemented before authoritative mapping and retained**.

`vetedge.services.nadis_reporting.get_nadis_vaccination_source` remains the query-paginated operational source preview using Vaccination + Patient truth and the existing Vaccination Report Branch/permission contract.

The authoritative workbook is now mapped, so source metadata reports `template_mapping_verified = true`. Source preview still reports `submission_ready = false`; readiness is calculated separately by the dedicated validation/export service because historical records may lack regulatory mappings.

## Phase 7B — Authoritative vaccination mapping and export

Status: **source-implemented; installed-site/browser/file QA pending**.

### Operational mappings added

- `Veterinary Species.nadis_species` — exact regulatory species wording.
- `Veterinary Vaccine.nadis_disease` — exact disease wording protected by the vaccine.
- `Veterinary Vaccine.nadis_vaccine_type` — NADIS vaccine type.
- `Veterinary Vaccine.nadis_source_of_vaccine` — source/manufacturer wording.
- `Veterinary Vaccine.nadis_panvac_tested` — `Yes` / `No`.
- `Veterinary Vaccination Record.vaccination_reason` — exact supplied-template classification:
  - `Control/Emergency vaccination`
  - `Preventive/Routine vaccination`.
- Branch custom fields:
  - `vetedge_nadis_admin_level_1`
  - `vetedge_nadis_admin_level_2`.

Branch geography is intentionally stored per Branch rather than as one global clinic setting so multi-branch clinics cannot silently export the wrong State/LGA.

### EdgeSuite vaccination workflow integration

The existing Vaccination Clinical Record Editor has an explicit field allowlist. `nadis_vaccination_editor.py` idempotently extends that existing configuration so `vaccination_reason` is visible/editable in the established EdgeSuite workflow rather than requiring a second regulatory vaccination form.

The field is regulatory classification only. It is safe to correct after invoice submission because it does not alter vaccine identity, price, submitted invoice, stock posting, batch allocation or administration evidence.

### Official export behavior

`vetedge.services.nadis_vaccination_export`:

- includes only `Administered` vaccination records;
- uses normal VetEdge/Frappe read permissions and established Branch report normalization;
- fetches operational records in bounded server pages;
- resolves Patient → Species mapping, Vaccine regulatory metadata and Branch regulatory geography;
- blocks export when required regulatory data is missing;
- groups individual vaccinations by the exact NADIS reporting dimensions;
- counts the grouped animals into `Number of animals vaccinated for the species selected`;
- generates an XLSX with the official sheet name, title, field-ID row, visible headers and data-start row;
- keeps official workbook export separate from generic EdgeSuite XLSX/CSV/PDF presentation exports.

Strict controlled values are enforced where the supplied workbook is complete and authoritative. The supplied geography/species lookup lists appear incomplete for Nigeria, so those lists are not used to reject otherwise valid mapped values; wording warnings are returned instead.

## Phase 7C — Disease outbreak capture model

Status: **source-implemented; installed-site QA pending**.

Consultation Diagnosis remains useful clinical evidence but is not treated as an outbreak event. A dedicated `Veterinary Disease Outbreak` parent record has been introduced with four child tables matching the official workbook relationship:

1. `Veterinary Outbreak Animal Group`
2. `Veterinary Outbreak Diagnosis Basis`
3. `Veterinary Outbreak Control Measure`
4. `Veterinary Outbreak Location`

### Parent outbreak captures

- Reporting Branch and Company
- Country (`Nigeria`)
- Branch NADIS Admin Level 1 snapshot
- Veterinary Diagnosis and NADIS disease snapshot
- Serotype
- New / Follow-up classification and original outbreak relationship
- Number of new outbreaks / total outbreaks
- Outbreak start, report, investigation and final-diagnosis dates
- Source of infection
- Continuing / Resolved state
- investigation notes.

### Child data captures

Animals affected:
- Species + NADIS species snapshot
- age group
- sex
- susceptible animals
- cases
- deaths
- slaughtered
- destroyed
- vaccinated around the outbreak.

Bases of diagnosis:
- Advanced laboratory test(s)
- Basic laboratory test(s)
- Clinical
- Owner's claim
- Post-mortem
- optional supporting Veterinary Lab Order.

Disease control measures:
- official control-measure wording
- Applied / Not Applicable / Planned
- optional applied date and notes.

Locations:
- locality name
- epidemiological unit type
- production system
- latitude / longitude.

`Veterinary Diagnosis.nadis_disease` provides the reusable regulatory mapping for disease names.

### Safety

The outbreak controller:

- derives/snapshots regulatory master values server-side;
- validates selected Branch against assigned Branches on save for non-global users;
- validates follow-up relationship;
- rejects negative population/outcome counts;
- validates chronological outbreak/investigation dates.

Until dedicated native List/Form permission-query hooks are landed and tested, the outbreak DocType itself is deliberately restricted to `System Manager` and `VetEdge Administrator`. This prevents broad native-list exposure while the regulatory workbench and export layer are completed. Broader Doctor/Nurse/Branch Manager access should be enabled only after fail-closed read hooks are added.

## Phase 7D — Disease outbreak official workbook export

Status: **source-implemented; installed-site/browser/file QA pending**.

`vetedge.services.nadis_outbreak_export` builds all five official sheets and keeps the parent relationship explicit:

- `Outbreaks.Code` = Veterinary Disease Outbreak name;
- each child sheet `parent` = that same outbreak name.

The export blocks when required regulatory data is missing, including missing disease mapping, investigation/final-diagnosis dates, affected animals, locations, required case counts or invalid controlled values.

Missing Basis of Diagnosis or Disease Control Measures currently produces warnings rather than automatic fabricated values.

Dates are written as true date cells with `DD/MM/YYYY` formatting.

## Phase 7E — EdgeSuite Regulatory Reporting workbench

Status: **source-implemented; browser QA pending**.

Route: `/desk/vetedge-regulatory-reporting`

The workbench provides common Branch / From Date / To Date scope and two regulatory cards:

### NADIS Monthly Vaccination Report

- Validate
- readiness counts
- blocking errors/warnings
- Download Official Excel.

### NADIS Disease Outbreak Report

- Validate
- readiness counts
- blocking errors/warnings
- Download Official Excel
- Outbreak Register / New Outbreak actions for authorised outbreak administrators.

The workbench is inserted idempotently into the Veterinary sidebar as `Regulatory Reporting → VCN / NADIS Reports` after standard sidebar synchronization on install/migrate.

## Validation state

### Implemented source contracts

`vetedge/tests/test_nadis_reporting_contract.py` covers:

- read-only, paginated vaccination source behavior;
- authoritative workbook filenames/hashes and visible mapping contract;
- correct placement of regulatory metadata on Species, Diagnosis, Vaccine, Vaccination and Branch;
- official vaccination export validation/aggregation boundaries;
- outbreak parent/child model shape;
- outbreak Branch/save safeguards;
- five official workbook sheets and parent relationships;
- no accounting/stock mutation or permission bypass in export services.

### Still required before merge/release

1. `bench --site <site> migrate` on a clean Frappe v16 VetEdge site.
2. Python compile / Ruff / focused source contracts.
3. Installed-site DocType/controller tests for outbreak create/update/permissions.
4. Vaccination EdgeSuite editor QA showing and saving Reason for Vaccination.
5. Regulatory Reporting page browser QA across supported roles.
6. Branch-scoped and multi-branch validation.
7. Generate both workbooks from fixture data and reopen them with `openpyxl`.
8. Compare generated workbook sheet names, rows, field IDs, headers, values, number/date formats and validation behavior against the supplied originals.
9. Open generated files in Microsoft Excel/LibreOffice to confirm no repair/security warnings and acceptable layout.
10. Add dedicated fail-closed native outbreak List/Form read hooks before expanding outbreak access beyond System Manager/VetEdge Administrator.

## Safety and compatibility

- No submitted Sales Invoice, Payment Entry, Stock Entry or other submitted ERPNext accounting/stock document is mutated.
- Vaccination regulatory metadata does not replace ERPNext billing or stock truth.
- An outbreak is never inferred merely from one or more Consultation Diagnosis rows.
- Existing Vaccination and Consultation workflows remain authoritative.
- New fields are optional for existing data; missing regulatory data is surfaced by export validation rather than silently backfilled with guessed values.
- Branch/company/role access remains server-authoritative.
- The two NADIS reports remain Standard compliance capability.
