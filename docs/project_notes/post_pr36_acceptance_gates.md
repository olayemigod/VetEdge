# Post-PR #36 Acceptance Gates

## Reporting / performance
- Interactive large reports use server pagination and bounded searches.
- Summary cards do not require browser-side full-dataset materialisation.
- Full export is separate from interactive pagination.
- Network QA records request count, transferred bytes, payload size and slowest requests.

## Export / print
- XLSX, CSV and PDF generated with correct MIME type and extension.
- Raw mode outputs table headings and rows only.
- Presentation options are independently selectable.
- Print and PDF share a paginated rendering contract.
- Automated validation reopens/parses generated files and rejects HTML/error bodies masquerading as downloads.

## Safety
- No submitted accounting-document mutation.
- No permission bypass.
- Branch/company/tenant/clinical/payment/stock validation remains server-side.
- No unnecessary polling or large hidden master preloads.

## Merge
- PR #36 merged first.
- Continuation PR retargeted to main and reconciled.
- Automated and manual QA pass before merge.
