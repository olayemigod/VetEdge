#!/usr/bin/env python3
"""Generate non-executable reconciliation resolution documents.

This tool reads Phase 2G review artifacts and writes human decision documents.
It does not import data, generate a clone, mutate records, or create scripts.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for reconciliation resolution"
STAGING_NOTICE = "STAGING REVIEW ONLY — NOT AN IMPORT PACKAGE"

ROLE_PATTERNS = [
	"VetEdge Administrator",
	"VetEdge Doctor",
	"VetEdge Receptionist",
	"VetEdge Billing User",
	"VetEdge Front Desk",
	"VetEdge Groomer",
	"VetEdge Nurse",
	"VetEdge Branch Manager",
	"VetEdge Portal User",
]

PORTAL_ROUTE_MAPPINGS = [
	("/vetedge_portal", "/veterinary_portal", "proposed redirect/manual review"),
	("/vetedge_guest_booking", "/veterinary_guest_booking", "proposed redirect/manual review"),
	("/desk/vetedge-executive-dashboard", "/desk/veterinary-executive-dashboard", "proposed clone landing route"),
]

MANUAL_STATUSES = {
	"email templates": "needs business decision",
	"roles": "manual decision required",
	"portal routes": "needs business decision",
	"Desk routes": "deferred",
	"reports": "accepted risk",
	"pages": "accepted risk",
	"workspaces": "accepted risk",
	"CoreEdge/product references": "blocked",
	"fixtures": "deferred",
	"DocType JSON identity fields": "blocked",
	"report JSON identity fields": "deferred",
}

EXCLUDED_IMPORT_SENSITIVE = {
	"Patch Log",
	"GL Entry",
	"Stock Ledger Entry",
	"DocField",
	"DocPerm",
	"DocType",
	"Module Def",
	"Role",
	"Has Role",
	"Workspace",
	"Page",
	"Installed Applications",
}


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate VetEdge reconciliation resolution package.")
	parser.add_argument("--review-package-dir", required=True)
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--verbose", action="store_true")
	parser.add_argument("--write", action="store_true")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def load_json(path: Path) -> Any:
	if not path.exists():
		raise FileNotFoundError(f"Required review artifact missing: {path}")
	return json.loads(path.read_text(encoding="utf-8"))


def read_csv(path: Path) -> list[dict[str, str]]:
	if not path.exists():
		raise FileNotFoundError(f"Required review artifact missing: {path}")
	with path.open(newline="", encoding="utf-8") as handle:
		return list(csv.DictReader(handle))


def read_text(path: Path) -> str:
	if not path.exists():
		raise FileNotFoundError(f"Required review artifact missing: {path}")
	return path.read_text(encoding="utf-8")


def discover_roles(matrix: list[dict[str, str]], dangerous: list[dict[str, str]], warnings: str) -> list[str]:
	found = set()
	blob = "\n".join(
		[
			warnings,
			"\n".join(json.dumps(row, sort_keys=True) for row in matrix),
			"\n".join(json.dumps(row, sort_keys=True) for row in dangerous),
		]
	)
	for role in ROLE_PATTERNS:
		if role in blob or role in {"VetEdge Administrator", "VetEdge Doctor", "VetEdge Receptionist", "VetEdge Billing User"}:
			found.add(role)
	for match in re.finditer(r"VetEdge [A-Za-z/ ]+(?:User|Doctor|Administrator|Manager|Nurse|Groomer|Desk|Receptionist)", blob):
		found.add(match.group(0).strip())
	return sorted(found)


def role_decision(role: str) -> tuple[str, str]:
	if role in {"VetEdge Administrator", "VetEdge Doctor", "VetEdge Front Desk", "VetEdge Receptionist", "VetEdge Billing User", "VetEdge Groomer", "VetEdge Nurse", "VetEdge Branch Manager", "VetEdge Portal User"}:
		target = role.replace("VetEdge", "Veterinary")
		return "rename to Veterinary equivalent", target
	return "manual decision required", ""


def role_mapping_markdown(roles: list[str]) -> str:
	lines = ["# Role / Permission Mapping", "", STAGING_NOTICE, "", "No roles are renamed by this document.", ""]
	lines.append("| Source Role | Recommendation | Proposed Target | Notes |")
	lines.append("| --- | --- | --- | --- |")
	for role in roles:
		decision, target = role_decision(role)
		lines.append(f"| {role} | {decision} | {target} | Review permissions before any future import. |")
	return "\n".join(lines) + "\n"


def portal_route_markdown() -> str:
	lines = ["# Portal Route Mapping", "", STAGING_NOTICE, "", "No redirects are created by this document.", ""]
	lines.append("| Source Route | Proposed Target | Recommendation |")
	lines.append("| --- | --- | --- |")
	for source, target, decision in PORTAL_ROUTE_MAPPINGS:
		lines.append(f"| `{source}` | `{target}` | {decision} |")
	return "\n".join(lines) + "\n"


def email_branding_markdown(manual_rows: list[dict[str, str]]) -> str:
	lines = ["# Email / Template Branding Review", "", STAGING_NOTICE, "", "No templates are modified by this document.", ""]
	lines.extend(
		[
			"- Templates with hardcoded `VetEdge` branding: should use client branding token or Veterinary default.",
			"- Operational/security templates: manual review required before rebranding.",
			"- Obsolete activation/onboarding templates: evaluate whether to retire.",
			"- Payment and clinical templates: safe to rebrand only after owner/client sign-off.",
			"",
			"## Classification",
			"",
			"| Area | Proposed Status | Notes |",
			"| --- | --- | --- |",
		]
	)
	for row in manual_rows:
		if "email" in (row.get("area") or "").lower():
			lines.append(f"| {row.get('area')} | should use client branding token | Review subject/body/footer. |")
	if not any("email" in (row.get("area") or "").lower() for row in manual_rows):
		lines.append("| email templates | manual review required | No explicit row found; preserve checklist item. |")
	return "\n".join(lines) + "\n"


def coreedge_mapping_markdown() -> str:
	return f"""# CoreEdge Mapping

{STAGING_NOTICE}

No CoreEdge records are modified by this document.

| Concept | Decision Draft |
| --- | --- |
| product_family | `veterinary_practice` |
| VetEdge distribution | `vetedge` |
| Future Veterinary distribution | `veterinary` |
| Existing VetEdge activation | Preserve until explicit client/site conversion decision. |
| Future Veterinary activation | Create separate activation path; do not reuse blindly. |
| Branding profile mapping | Map brand profile by tenant/client, not by package name only. |
| SMS/email/WhatsApp/EdgeFinder | Reuse shared services through provider-agnostic CoreEdge contracts. |
| Stock Expiry gate | Same capability gate, distribution-aware. |
| Financial Dashboard gate | Same capability gate, distribution-aware. |
| Hospitalisation Dashboard gate | Same capability gate, distribution-aware. |
"""


def hospitalisation_metadata_markdown(warnings: str) -> str:
	found = "activities_tab" in warnings
	recommendation = (
		"Treat `activities_tab` as UI tab metadata, not a data column. Keep runtime unchanged. "
		"The sampler should ignore or fall back around non-queryable layout/tab fields."
		if found
		else "No hospitalisation metadata warning was found in the review package."
	)
	return f"""# Hospitalisation Metadata Review

{STAGING_NOTICE}

## Finding

`activities_tab` warning detected: {str(found).lower()}

## Recommendation

{recommendation}

## Decision

fix sampler metadata filtering / keep runtime unchanged
"""


def manual_review_resolution_rows(manual_rows: list[dict[str, str]]) -> list[dict[str, str]]:
	rows = []
	for row in manual_rows:
		area = row.get("area") or ""
		rows.append(
			{
				"area": area,
				"status": MANUAL_STATUSES.get(area, "needs business decision"),
				"resolution": "Documented for future migration design; no runtime/import action taken.",
				"owner": "",
				"notes": row.get("reason") or "",
			}
		)
	return rows


def future_import_contract_markdown(dangerous: list[dict[str, str]]) -> str:
	excluded = sorted({row.get("doctype") or "" for row in dangerous if row.get("doctype")})
	excluded_text = "\n".join(f"- {doctype}" for doctype in excluded)
	return f"""# Future Import Contract Draft

{STAGING_NOTICE}

This is a non-executable migration contract draft. It is documentation only.

## Allowed DocTypes

Only DocTypes classified as directly portable may be considered, after link validation and mapping approval.

## Excluded DocTypes

{excluded_text}

## Required Mappings

- company
- branch
- cost center
- customer / owner
- user
- role
- route
- file reference
- item / warehouse / price list
- CoreEdge product distribution

## Import Order

1. ERPNext masters
2. Core clinical masters/settings
3. Patients/owners
4. Appointments
5. Consultations
6. Vaccination/preventive care
7. Lab/grooming/boarding/hospitalisation operational records
8. Items/stock dependencies
9. Billing references
10. Files/attachments
11. Communications/comments
12. Notifications/preferences
13. Portal/email/client branding records
14. CoreEdge activation/branding/service settings

## Validation Checks

- record counts reconciled
- links resolved
- sensitive data redacted in review exports
- dangerous/system DocTypes excluded
- submitted accounting/stock internals not rewritten
- dashboard/sidebar/routes manually reviewed

## Rollback Assumptions

Rollback must be site-level and rehearsal-tested before production cutover.

## Sign-Off Requirements

Business owner, implementation lead, accounting owner, clinical operations owner, and platform/CoreEdge owner must sign off.
"""


def unresolved_blockers_markdown(summary: dict[str, Any], warnings: str, dangerous: list[dict[str, str]]) -> str:
	blockers = []
	if summary.get("readiness_status") != "ready_for_staging_review":
		blockers.append(f"Readiness status is `{summary.get('readiness_status')}`.")
	if "activities_tab" in warnings:
		blockers.append("Hospitalisation metadata sampler warning requires review.")
	if any((row.get("doctype") in EXCLUDED_IMPORT_SENSITIVE) for row in dangerous):
		blockers.append("Dangerous/system DocTypes remain excluded and require future explicit policy.")
	if not blockers:
		blockers.append("No blockers identified by the current review artifacts.")
	return "# Unresolved Blockers\n\n" + STAGING_NOTICE + "\n\n" + "\n".join(f"- {item}" for item in blockers) + "\n"


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=columns)
		writer.writeheader()
		for row in rows:
			writer.writerow({column: row.get(column, "") for column in columns})


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def generate_resolution(review_package_dir: Path, output_dir: Path) -> dict[str, Any]:
	summary = load_json(review_package_dir / "reconciliation_summary.json")
	matrix = read_csv(review_package_dir / "reconciliation_matrix.csv")
	manual = read_csv(review_package_dir / "manual_review_items.csv")
	dangerous = read_csv(review_package_dir / "dangerous_exclusions.csv")
	warnings = read_text(review_package_dir / "warnings.md")
	_cutover = read_text(review_package_dir / "cutover_questions.md")
	roles = discover_roles(matrix, dangerous, warnings)
	manual_resolution = manual_review_resolution_rows(manual)
	blocked = [row for row in manual_resolution if row["status"] == "blocked"]
	resolution_summary = {
		"notice": STAGING_NOTICE,
		"source_readiness_status": summary.get("readiness_status"),
		"source_readiness_score": summary.get("readiness_score"),
		"roles_reviewed": roles,
		"manual_review_items": len(manual_resolution),
		"blocked_items": [row["area"] for row in blocked],
		"hospitalisation_metadata_recommendation": "fix sampler metadata filtering / keep runtime unchanged"
		if "activities_tab" in warnings
		else "no hospitalisation metadata warning found",
		"future_import_contract": "non-executable documentation only",
		"import_behavior_created": False,
		"clone_generated": False,
		"business_data_mutated": False,
	}

	output_dir.mkdir(parents=True, exist_ok=True)
	write_json(output_dir / "resolution_summary.json", resolution_summary)
	(output_dir / "role_permission_mapping.md").write_text(role_mapping_markdown(roles), encoding="utf-8")
	(output_dir / "portal_route_mapping.md").write_text(portal_route_markdown(), encoding="utf-8")
	(output_dir / "email_branding_review.md").write_text(email_branding_markdown(manual), encoding="utf-8")
	(output_dir / "coreedge_mapping.md").write_text(coreedge_mapping_markdown(), encoding="utf-8")
	(output_dir / "hospitalisation_metadata_review.md").write_text(hospitalisation_metadata_markdown(warnings), encoding="utf-8")
	write_csv(output_dir / "manual_review_resolution.csv", ["area", "status", "resolution", "owner", "notes"], manual_resolution)
	(output_dir / "future_import_contract_draft.md").write_text(future_import_contract_markdown(dangerous), encoding="utf-8")
	(output_dir / "unresolved_blockers.md").write_text(unresolved_blockers_markdown(summary, warnings, dangerous), encoding="utf-8")
	return resolution_summary


def validate_no_forbidden_outputs(output_dir: Path) -> list[str]:
	if not output_dir.exists():
		return []
	forbidden = []
	for path in output_dir.rglob("*"):
		if path.is_file() and (path.suffix in {".sql", ".sh"} or path.name in {"import.py", "restore.py", "migrate.py"}):
			forbidden.append(str(path))
	return forbidden


def print_summary(summary: dict[str, Any], output_dir: Path, verbose: bool) -> None:
	print("VetEdge reconciliation resolution package")
	print(f"Output directory: {output_dir}")
	print(f"Source readiness: {summary['source_readiness_status']} ({summary['source_readiness_score']})")
	print(f"Roles reviewed: {len(summary['roles_reviewed'])}")
	print(f"Manual review items: {summary['manual_review_items']}")
	print(f"Blocked items: {len(summary['blocked_items'])}")
	print(f"Hospitalisation metadata: {summary['hospitalisation_metadata_recommendation']}")
	if verbose:
		for item in summary["blocked_items"]:
			print(f"  - blocked: {item}")


def main() -> int:
	args = parse_args()
	output_dir = Path(args.output_dir)
	summary = generate_resolution(Path(args.review_package_dir), output_dir)
	forbidden = validate_no_forbidden_outputs(output_dir)
	if forbidden:
		raise RuntimeError(f"Forbidden output files generated: {forbidden}")
	print_summary(summary, output_dir, args.verbose)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
