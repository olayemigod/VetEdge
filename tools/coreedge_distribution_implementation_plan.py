#!/usr/bin/env python3
"""Generate CoreEdge distribution implementation planning artifacts.

This is planning/reporting only. It does not modify CoreEdge or VetEdge runtime
behavior, generate a clone, import data, mutate business data, rename roles,
create redirects, or write executable SQL/shell/import/restore/migrate scripts.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for CoreEdge distribution implementation planning"
NOTICE = "IMPLEMENTATION PLANNING ONLY - NO RUNTIME CHANGES"

EXCLUDED_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules", "dist", "build", "logs"}
TEXT_SUFFIXES = {".py", ".json", ".toml", ".txt", ".md", ".yml", ".yaml", ".js", ".html", ".css", ".csv"}
FORBIDDEN_OUTPUT_NAMES = {"import.py", "restore.py", "migrate.py"}
FORBIDDEN_OUTPUT_SUFFIXES = {".sql", ".sh"}

INVENTORY_TERMS = [
	"CoreEdge Product Activation",
	"Product Activation",
	"Activation Status",
	"product",
	"product_code",
	"product_family",
	"distribution",
	"feature",
	"feature_gate",
	"adapter",
	"vetedge",
	"VetEdge",
	"SMS",
	"Email",
	"WhatsApp",
	"EdgeFinder",
	"wallet",
	"branding",
	"notification",
]

COREEDGE_CHANGE_ROWS = [
	{
		"change_id": "COREEDGE-001",
		"repo": "coreedge",
		"file_or_doctype": "CoreEdge Product Activation",
		"area": "activation schema",
		"proposed_change": "Plan product_family and distribution fields or an equivalent compatibility mapping layer.",
		"risk": "medium",
		"migration_needed": "yes - migration patch/backfill plan required if fields are added",
		"tests_required": "activation schema/backward compatibility tests",
		"status": "planned_not_implemented",
	},
	{
		"change_id": "COREEDGE-002",
		"repo": "coreedge",
		"file_or_doctype": "activation resolver/runtime access services",
		"area": "activation resolver",
		"proposed_change": "Resolve activation by tenant + product_family + distribution; keep legacy product/app fallback.",
		"risk": "high",
		"migration_needed": "compatibility mapping for existing VetEdge activations",
		"tests_required": "VetEdge legacy and Veterinary new activation separation tests",
		"status": "planned_not_implemented",
	},
	{
		"change_id": "COREEDGE-003",
		"repo": "coreedge",
		"file_or_doctype": "feature gate services",
		"area": "feature gates",
		"proposed_change": "Make gates distribution-aware while keeping capability keys product_family scoped.",
		"risk": "high",
		"migration_needed": "no data migration if implemented as resolver compatibility layer",
		"tests_required": "Stock Expiry, Financial Dashboard, Hospitalisation Dashboard distribution gate tests",
		"status": "planned_not_implemented",
	},
	{
		"change_id": "COREEDGE-004",
		"repo": "coreedge",
		"file_or_doctype": "branding/profile services",
		"area": "branding",
		"proposed_change": "Resolve branding by tenant and distribution; avoid package-name-only identity.",
		"risk": "medium",
		"migration_needed": "possible branding profile compatibility mapping",
		"tests_required": "branding fallback and override tests",
		"status": "planned_not_implemented",
	},
	{
		"change_id": "COREEDGE-005",
		"repo": "coreedge",
		"file_or_doctype": "SMS/Email/WhatsApp/EdgeFinder/wallet services",
		"area": "shared services",
		"proposed_change": "Ensure service accounts and wallet usage are tenant/service scoped, not hardcoded to VetEdge package identity.",
		"risk": "medium",
		"migration_needed": "no direct business-data migration",
		"tests_required": "shared service resolver tests for vetedge and veterinary distributions",
		"status": "planned_not_implemented",
	},
	{
		"change_id": "COREEDGE-006",
		"repo": "coreedge",
		"file_or_doctype": "product adapter registry",
		"area": "adapter contract",
		"proposed_change": "Define resolver API for product identity, family, distribution, access, branding, and service config.",
		"risk": "medium",
		"migration_needed": "adapter compatibility review",
		"tests_required": "adapter contract tests",
		"status": "planned_not_implemented",
	},
]

VETEDGE_ADAPTER_CHANGE_ROWS = [
	{
		"change_id": "VETEDGE-ADAPTER-001",
		"repo": "vetedge",
		"file_or_doctype": "VetEdge CoreEdge adapter",
		"area": "product identity",
		"proposed_change": "Expose resolve_product_identity(), get_product_family(), and get_distribution() as adapter contract methods.",
		"risk": "medium",
		"migration_needed": "no",
		"tests_required": "VetEdge adapter compatibility tests",
		"status": "planned_not_implemented",
	},
	{
		"change_id": "VETEDGE-ADAPTER-002",
		"repo": "vetedge",
		"file_or_doctype": "feature access service calls",
		"area": "feature gates",
		"proposed_change": "Call require_access(feature_key) through CoreEdge adapter with distribution-aware identity.",
		"risk": "medium",
		"migration_needed": "no",
		"tests_required": "no regression for current VetEdge access gates",
		"status": "planned_not_implemented",
	},
	{
		"change_id": "VETEDGE-ADAPTER-003",
		"repo": "vetedge",
		"file_or_doctype": "branding/service config integration points",
		"area": "shared services",
		"proposed_change": "Resolve branding and service configuration through provider-agnostic adapter APIs.",
		"risk": "low",
		"migration_needed": "no",
		"tests_required": "branding fallback and missing CoreEdge fallback tests",
		"status": "planned_not_implemented",
	},
]


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Generate CoreEdge distribution implementation planning package.")
	parser.add_argument("--coreedge-dir", required=True)
	parser.add_argument("--vetedge-dir", required=True)
	parser.add_argument("--validator-dir")
	parser.add_argument("--contract-dir")
	parser.add_argument("--output-dir", required=True)
	parser.add_argument("--verbose", action="store_true")
	parser.add_argument("--write", action="store_true")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def load_json(path: Path, *, required: bool = False) -> Any:
	if not path.exists():
		if required:
			raise FileNotFoundError(f"Required artifact missing: {path}")
		return None
	return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path, *, required: bool = False) -> str:
	if not path.exists():
		if required:
			raise FileNotFoundError(f"Required artifact missing: {path}")
		return ""
	return path.read_text(encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("w", newline="", encoding="utf-8") as handle:
		writer = csv.DictWriter(handle, fieldnames=columns)
		writer.writeheader()
		for row in rows:
			writer.writerow({column: row.get(column, "") for column in columns})


def should_skip(relative_path: Path) -> bool:
	return any(part in EXCLUDED_DIRS for part in relative_path.parts) or relative_path.suffix in {".pyc", ".pyo"}


def is_text_file(path: Path) -> bool:
	return path.suffix in TEXT_SUFFIXES or path.name in {"hooks.py", "modules.txt", "patches.txt"}


def inventory_area(relative_path: str, matched_text: str) -> str:
	lower = relative_path.lower()
	match = matched_text.lower()
	if "/doctype/" in lower or "activation" in match:
		return "activation"
	if "runtime_access" in lower or "access" in lower:
		return "runtime access"
	if "adapter" in lower or "adapter" in match:
		return "adapter"
	if "branding" in lower or "branding" in match:
		return "branding"
	if any(service in lower or service in match for service in ["sms", "email", "whatsapp", "wallet", "edgefinder", "notification"]):
		return "shared services"
	if "feature" in match:
		return "feature gates"
	if "product" in match or "distribution" in match:
		return "product identity"
	return "source reference"


def scan_source_inventory(root: Path, repo: str) -> list[dict[str, Any]]:
	if not root.exists():
		return []
	rows: list[dict[str, Any]] = []
	for path in sorted(root.rglob("*")):
		if not path.is_file():
			continue
		relative_path = path.relative_to(root)
		if should_skip(relative_path) or not is_text_file(path):
			continue
		try:
			lines = path.read_text(encoding="utf-8").splitlines()
		except UnicodeDecodeError:
			continue
		for line_number, line in enumerate(lines, start=1):
			for term in INVENTORY_TERMS:
				if term in line:
					rows.append(
						{
							"repo": repo,
							"file_path": relative_path.as_posix(),
							"line_number": line_number,
							"matched_text": term,
							"area": inventory_area(relative_path.as_posix(), term),
							"notes": "static inventory only; no source changed",
						}
					)
	return rows


def product_family_distribution_design_md() -> str:
	return f"""# Product Family / Distribution Design

{NOTICE}

## Target Model

- `product_family = veterinary_practice`
- `distribution = vetedge`
- `distribution = veterinary`

## Decision

`product_family` groups related clinical capability. VetEdge and Veterinary both belong to `veterinary_practice`.

`distribution` distinguishes product packaging, deployment identity, activation path, and subscription/package policy.

VetEdge and Veterinary share a family but must have separate activation identities. CoreEdge must not rely only on package/app name when resolving access or branding.
"""


def activation_model_design_md() -> str:
	return f"""# Activation Model Design

{NOTICE}

## Target Representation

CoreEdge should resolve activation by tenant/client plus product identity:

- product_family
- distribution
- tenant/company/site identity
- activation status: trial, grace, active, expired, suspended

## Decisions To Implement Later

- Existing CoreEdge Product Activation likely needs `product_family` and `distribution` fields, or a compatibility mapping layer that behaves equivalently.
- VetEdge SaaS activation and Veterinary white-label activation must be separate records/paths.
- Existing VetEdge activation records must not be blindly converted.
- Adapter resolver changes are required so access checks do not assume package name equals product identity.
- Any schema change needs a migration patch and backward compatibility.

## Fallback Behavior

- If CoreEdge is missing and the feature has a local safe fallback, VetEdge may fail open only for non-billable, non-sensitive read paths.
- Access-controlled, billable, or service-usage paths should fail closed or degrade with an explicit unavailable state.
- Existing VetEdge behavior must remain compatible until CoreEdge migration is complete.
"""


def feature_gate_design_md() -> str:
	return f"""# Feature Gate Design

{NOTICE}

## Recommended Model

- Feature capability belongs to `product_family`.
- Subscription/package access belongs to `distribution + tenant`.
- Service usage belongs to CoreEdge service account, wallet, and provider configuration.
- Feature checks should use explicit feature keys.

## Required Distribution-Aware Gates

- Stock Expiry
- Financial Dashboard
- Hospitalisation Dashboard
- Appointment
- Boarding
- Grooming
- Lab
- Vaccination
- Billing
- SMS service usage
- Email service usage
- WhatsApp service usage
- EdgeFinder

## Decision

Use `product_family + distribution + tenant + feature_key` for access resolution. Do not gate Veterinary by reusing VetEdge activation blindly.
"""


def shared_services_design_md() -> str:
	return f"""# Shared Services Design

{NOTICE}

VetEdge and future Veterinary should consume shared services through CoreEdge contracts, not product-specific hardcoding.

## Services

- SMS
- Email
- WhatsApp
- EdgeFinder
- Wallet/service usage
- Branding profile
- Notifications

## Decision

Service configuration should resolve by tenant and service account. Product distribution may influence package entitlement, branding, templates, and allowed service usage, but provider credentials and wallet accounting must remain CoreEdge-owned.
"""


def branding_and_identity_design_md() -> str:
	return f"""# Branding And Identity Design

{NOTICE}

## Rules

- Product identity is not the same as Python package name.
- VetEdge SaaS identity remains VetEdge.
- Future Veterinary white-label identity uses Veterinary defaults unless client branding overrides exist.
- Existing VetEdge clients may use branding overrides without app identity migration.
- Branding resolution should prefer tenant branding profile, then distribution default, then product family default.

No branding records are modified by this plan.
"""


def adapter_contract_design_md() -> str:
	return f"""# Adapter Contract Design

{NOTICE}

Expected adapter API contract for VetEdge and future Veterinary:

```python
resolve_product_identity()
get_product_family()
get_distribution()
require_access(feature_key)
resolve_branding()
resolve_service_config(service_key)
```

## Decision

VetEdge and Veterinary adapters should expose identical contract shape while returning different distributions. This lets CoreEdge resolve access, branding, and service configuration without treating package name as product identity.
"""


def test_plan_md() -> str:
	return f"""# Test Plan

{NOTICE}

- CoreEdge product family/distribution resolver tests.
- VetEdge adapter compatibility tests.
- Future Veterinary adapter tests.
- Activation separation tests for VetEdge and Veterinary.
- Feature gate distribution-awareness tests.
- Stock Expiry gate tests.
- Financial Dashboard gate tests.
- Hospitalisation Dashboard gate tests.
- Branding fallback tests.
- Missing CoreEdge fallback tests.
- Shared SMS/Email/WhatsApp/EdgeFinder/wallet service resolver tests.
- no regression for current VetEdge access gates.
"""


def migration_impact_assessment_md() -> str:
	return f"""# Migration Impact Assessment

{NOTICE}

- Existing VetEdge clients should continue working.
- Existing white-label clients on VetEdge should not be forced to migrate.
- Future Veterinary clients should use separate activation.
- Existing activation records should not be blindly converted.
- Any CoreEdge schema change needs a migration patch and backward compatibility.
- Business-data migration/import remains out of scope.
- Submitted ERPNext accounting and stock records must not be rewritten for product identity.
"""


def phase_2l_recommendation_md(summary: dict[str, Any]) -> str:
	return f"""# Phase 2L Recommendation

{NOTICE}

## Result

- CoreEdge source inventory generated: `{summary['coreedge_source_available']}`
- Required CoreEdge changes: `{summary['required_coreedge_change_count']}`
- Required VetEdge adapter changes: `{summary['required_vetedge_adapter_change_count']}`
- Clone generated: `{str(summary['clone_generated']).lower()}`
- Import behavior created: `{str(summary['import_behavior_created']).lower()}`
- Business data mutated: `{str(summary['business_data_mutated']).lower()}`

## Recommended Phase 2M

Begin CoreEdge contract implementation design review or implement a non-runtime test harness for the adapter contract. Do not generate the Veterinary clone, enable clone write mode, or add import behavior yet.
"""


def build_summary(coreedge_dir: Path, inventory: list[dict[str, Any]], validator_summary: dict[str, Any] | None) -> dict[str, Any]:
	coreedge_available = coreedge_dir.exists()
	return {
		"notice": NOTICE,
		"coreedge_source_available": coreedge_available,
		"coreedge_inventory_count": len([row for row in inventory if row.get("repo") == "coreedge"]),
		"vetedge_inventory_count": len([row for row in inventory if row.get("repo") == "vetedge"]),
		"required_coreedge_change_count": len(COREEDGE_CHANGE_ROWS),
		"required_vetedge_adapter_change_count": len(VETEDGE_ADAPTER_CHANGE_ROWS),
		"activation_model_decision": "Use tenant + product_family + distribution activation resolution with backward-compatible legacy VetEdge mapping.",
		"feature_gate_model_decision": "Use product_family + distribution + tenant + explicit feature_key; service usage resolves through CoreEdge service account/wallet/provider config.",
		"shared_services_decision": "SMS, Email, WhatsApp, EdgeFinder, wallet, branding, and notifications stay CoreEdge-owned and distribution-aware.",
		"validator_coreedge_contract_valid": (validator_summary or {}).get("coreedge_contract_valid"),
		"validator_doctype_identity_policy_valid": (validator_summary or {}).get("doctype_identity_policy_valid"),
		"clone_generated": False,
		"clone_write_mode_enabled": False,
		"import_behavior_created": False,
		"business_data_mutated": False,
	}


def generate_implementation_plan(
	coreedge_dir: Path,
	vetedge_dir: Path,
	validator_dir: Path | None,
	contract_dir: Path | None,
	output_dir: Path,
) -> dict[str, Any]:
	validator_summary = load_json(validator_dir / "validator_summary.json", required=False) if validator_dir else None
	if contract_dir:
		read_text(contract_dir / "coreedge_distribution_contract.md", required=False)
	inventory = []
	inventory.extend(scan_source_inventory(coreedge_dir, "coreedge"))
	inventory.extend(scan_source_inventory(vetedge_dir, "vetedge"))
	summary = build_summary(coreedge_dir, inventory, validator_summary)

	output_dir.mkdir(parents=True, exist_ok=True)
	write_json(output_dir / "implementation_plan_summary.json", summary)
	write_csv(
		output_dir / "coreedge_source_inventory.csv",
		["repo", "file_path", "line_number", "matched_text", "area", "notes"],
		inventory,
	)
	(output_dir / "product_family_distribution_design.md").write_text(product_family_distribution_design_md(), encoding="utf-8")
	(output_dir / "activation_model_design.md").write_text(activation_model_design_md(), encoding="utf-8")
	(output_dir / "feature_gate_design.md").write_text(feature_gate_design_md(), encoding="utf-8")
	(output_dir / "shared_services_design.md").write_text(shared_services_design_md(), encoding="utf-8")
	(output_dir / "branding_and_identity_design.md").write_text(branding_and_identity_design_md(), encoding="utf-8")
	(output_dir / "adapter_contract_design.md").write_text(adapter_contract_design_md(), encoding="utf-8")
	write_csv(
		output_dir / "required_coreedge_changes.csv",
		["change_id", "repo", "file_or_doctype", "area", "proposed_change", "risk", "migration_needed", "tests_required", "status"],
		COREEDGE_CHANGE_ROWS,
	)
	write_csv(
		output_dir / "required_vetedge_adapter_changes.csv",
		["change_id", "repo", "file_or_doctype", "area", "proposed_change", "risk", "migration_needed", "tests_required", "status"],
		VETEDGE_ADAPTER_CHANGE_ROWS,
	)
	(output_dir / "test_plan.md").write_text(test_plan_md(), encoding="utf-8")
	(output_dir / "migration_impact_assessment.md").write_text(migration_impact_assessment_md(), encoding="utf-8")
	(output_dir / "phase_2l_recommendation.md").write_text(phase_2l_recommendation_md(summary), encoding="utf-8")
	return summary


def validate_no_forbidden_outputs(output_dir: Path) -> list[str]:
	if not output_dir.exists():
		return []
	forbidden = []
	for path in output_dir.rglob("*"):
		if path.is_file() and (path.name in FORBIDDEN_OUTPUT_NAMES or path.suffix in FORBIDDEN_OUTPUT_SUFFIXES):
			forbidden.append(str(path))
	return forbidden


def print_summary(summary: dict[str, Any], output_dir: Path, verbose: bool) -> None:
	print("CoreEdge distribution implementation plan")
	print(f"Output directory: {output_dir}")
	print(f"CoreEdge source available: {summary['coreedge_source_available']}")
	print(f"Required CoreEdge changes: {summary['required_coreedge_change_count']}")
	print(f"Required VetEdge adapter changes: {summary['required_vetedge_adapter_change_count']}")
	print(f"Clone generated: {summary['clone_generated']}")
	print(f"Import behavior created: {summary['import_behavior_created']}")
	print(f"Business data mutated: {summary['business_data_mutated']}")
	if verbose:
		print(f"CoreEdge inventory rows: {summary['coreedge_inventory_count']}")
		print(f"VetEdge inventory rows: {summary['vetedge_inventory_count']}")
		print(f"Activation model: {summary['activation_model_decision']}")
		print(f"Feature gate model: {summary['feature_gate_model_decision']}")


def main() -> int:
	args = parse_args()
	output_dir = Path(args.output_dir)
	summary = generate_implementation_plan(
		Path(args.coreedge_dir),
		Path(args.vetedge_dir),
		Path(args.validator_dir) if args.validator_dir else None,
		Path(args.contract_dir) if args.contract_dir else None,
		output_dir,
	)
	forbidden = validate_no_forbidden_outputs(output_dir)
	if forbidden:
		raise RuntimeError(f"Forbidden output files generated: {forbidden}")
	print_summary(summary, output_dir, args.verbose)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
