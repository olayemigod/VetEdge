# VCN / NADIS Official Template Acceptance Contract

## Purpose

This note defines the release gate for VetEdge's VCN / NADIS regulatory workbooks. The regulatory exporters must use the authoritative spreadsheets supplied for the implementation and must not silently reconstruct, substitute or guess their workbook structure.

## Authoritative templates

### Monthly Vaccination Report

- File: `Nadis Template Vaccination Report 1.xlsx`
- SHA-256: `458e7af8b47c491f5245f5fc6cc8bbe754bbc23ab63829e88bb2083b813c05ba`
- Primary sheet: `Vaccinations`

### Disease Outbreak Report

- File: `NadisTemplate Disease Outbreak Report.xlsx`
- SHA-256: `8ea90b4b5c30a66029186905e9aab846bf897f40121d5ec7d7d69acf2964db94`
- Required sheets:
  - `Outbreaks`
  - `Animals affected`
  - `Bases of Diagnosis`
  - `Disease Control Measures`
  - `Locations`

## Packaging contract

The source XLSX files are stored as numbered base64 text assets under `vetedge/templates/nadis/` because the regulatory branch transport path is text-safe. `scripts/package_nadis_templates.py` is the only supported regeneration path.

The packager must:

1. verify each source XLSX against its authoritative SHA-256 before packaging;
2. remove stale single-file or multipart assets for the same template;
3. emit deterministic `part00`, `part01`, ... base64 parts;
4. reconstruct the written parts and verify the authoritative SHA-256 again.

Runtime loading must fail closed when:

- no packaged asset exists;
- both single-file and multipart representations exist;
- multipart numbering has a gap or is out of sequence;
- base64 decoding fails; or
- reconstructed XLSX bytes do not match the authoritative SHA-256.

## Export contract

`submission_ready` is not based only on clinical/regulatory data completeness. The backend must also successfully load and verify the installed official template.

The exporters populate only official report data cells through the package-preserving XLSX writer. They must not create replacement workbooks with `openpyxl.Workbook()` or restyle/rebuild the official sheets.

The package writer may modify the relevant worksheet XML files needed to populate report rows. All unrelated XLSX package members must remain untouched so that official hidden lookup values, validation definitions, named ranges, comments/drawings and workbook metadata are preserved.

## Vaccination acceptance

- Only `Administered` vaccination records are eligible.
- Required NADIS mappings must be complete before generation.
- The report counts distinct animals within each official NADIS grouping rather than raw vaccination document rows.
- Report grouping must retain Branch geography, year/month, vaccination reason, species, disease, vaccine, vaccine type/source, batch and PANVAC status.
- The generated workbook must retain the official hidden/reference and validation structure.

## Disease Outbreak acceptance

- A real `Veterinary Disease Outbreak` record is authoritative; consultations alone must not be promoted into official outbreak events.
- Parent outbreak rows and all four child-sheet collections must retain their parent linkage.
- Required population, diagnosis, control and location validation must run before generation.
- New outbreak and follow-up semantics, count integrity and coordinate validation must remain server-authoritative.
- The generated workbook must retain all five official sheets and their original hidden/reference and validation structure.

## QA gates before merge

Automated/source-level acceptance:

- exact packaged-template hashes pass;
- multipart loader fail-closed contracts pass;
- package-preserving writer contracts pass;
- vaccination aggregation contracts pass;
- outbreak safety and Branch-permission contracts pass;
- Regulatory Report Run lifecycle contracts pass;
- EdgeSuite Regulatory Reporting workbench contracts pass.

Installed-site acceptance remains required after PR #47 reaches a stable QA checkpoint:

1. reconcile PR #50 onto the accepted PR #47 head;
2. run Frappe v16 install/migrate validation;
3. run the full relevant Python/Ruff/unit/integration suite;
4. generate both workbooks from installed-site fixture records;
5. reopen generated files programmatically;
6. run `scripts/verify_nadis_workbooks.py` against the generated files and authoritative templates;
7. open both generated files in Microsoft Excel or LibreOffice with no repair warning;
8. QA Company/Branch/role isolation in the EdgeSuite Regulatory Reporting workbench;
9. test Generate & Save, frozen private attachment, email submission and Accepted/Rejected/Superseded lifecycle;
10. confirm submitted ERPNext accounting/stock documents remain untouched.

## Merge boundary

PR #47 remains the authoritative source for its ongoing QA/fix scope. PR #50 must add the VCN/NADIS regulatory feature without reverting or independently reimplementing PR #47 Administration, Branch Access, Care Location, navigation, reporting, security or other continuation work.
