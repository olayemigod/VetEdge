#!/usr/bin/env python3
"""Audit-only preview for a future VetEdge -> Veterinary downstream clone.

Phase 2A intentionally does not write a clone. The script builds a source
inventory, previews controlled path/text transformations, and emits warnings
for human review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


WRITE_DISABLED_MESSAGE = "write mode intentionally disabled for Phase 2A"
DEFAULT_REGISTRY_PATH = Path(__file__).with_name("veterinary_clone_audit_registry.json")

EXCLUDED_DIRS = {
	".git",
	".pytest_cache",
	"__pycache__",
	"node_modules",
	"dist",
	"build",
	"logs",
	".mypy_cache",
	".ruff_cache",
}

EXCLUDED_SUFFIXES = {
	".pyc",
	".pyo",
	".png",
	".jpg",
	".jpeg",
	".gif",
	".ico",
	".pdf",
	".zip",
	".tar",
	".gz",
	".sqlite",
	".db",
	".log",
}

TEXT_SUFFIXES = {
	".py",
	".js",
	".json",
	".html",
	".css",
	".md",
	".toml",
	".txt",
	".yml",
	".yaml",
	".scss",
}

PROTECTED_TERMS = {
	"Veterinary Patient",
	"Veterinary Appointment",
	"Veterinary Consultation",
	"Veterinary Hospitalisation",
	"Veterinary Records",
	"Veterinary Settings",
	"Veterinary Notification Item",
	"Veterinary Vital Signs",
	"Veterinary Financial Dashboard",
	"Veterinary Hospitalisation Dashboard",
	"Stock Expiry Status",
}

CLONE_AUDIT_REGISTRY = {
	"protected_clinical_domain_names": sorted(PROTECTED_TERMS),
	"allowed_generic_veterinary_labels": [
		"Veterinary",
		"Veterinary Records",
		"Veterinary Masters",
		"Veterinary Financial Dashboard",
		"Veterinary Hospitalisation Dashboard",
	],
	"expected_retained_report_names": [
		"Active Hospitalisations",
		"Care Location Occupancy",
		"Hospitalisation Charge Summary",
		"Pending Hospitalisation Actions",
		"Stock Expiry Status",
	],
	"expected_retained_doctype_names": [
		"Veterinary Appointment",
		"Veterinary Consultation",
		"Veterinary Hospitalisation",
		"Veterinary Notification Item",
		"Veterinary Patient",
		"Veterinary Settings",
		"Veterinary Vital Signs",
	],
	"expected_sidebar_labels": [
		"Executive Dashboard",
		"Dashboards",
		"Veterinary Records",
		"Hospitalisation",
		"Pet Grooming",
		"Pet Boarding",
		"Veterinary Masters",
		"Reports",
		"Billing",
		"Setup",
	],
	"expected_dashboard_labels": [
		"Executive Dashboard",
		"Financial Dashboard",
		"Hospitalisation Dashboard",
	],
	"generated_cache_build_exclusions": sorted(EXCLUDED_DIRS | EXCLUDED_SUFFIXES),
}

DANGEROUS_REFERENCE_REGISTRY = {
	"patch_lineage": "Patch files and patches.txt must not be blindly renamed because patch history is migration state.",
	"role_name": "Role names are permission identities and need an explicit role migration decision.",
	"portal_route": "Portal routes are public URLs and may be bookmarked or linked externally.",
	"desk_route": "Desk routes must change only with matching Page JSON, JS, sidebar, launcher, and tests.",
	"coreedge_reference": "CoreEdge product/distribution strings need explicit platform support.",
	"whitelisted_method_reference": "Whitelisted dotted paths must remain callable from JS/templates/API clients.",
	"scheduler_event_dotted_path": "Scheduler event dotted paths must import after transformation.",
	"doc_event_dotted_path": "Doc event dotted paths must import after transformation.",
	"fixture_record_identity": "Fixture record names are persisted identifiers and require review.",
	"email_template_identity": "Email template record names and bodies include product branding.",
	"doctype_json_identity": "DocType JSON identity-sensitive fields affect database tables and links.",
	"report_json_identity": "Report JSON identity-sensitive fields affect route/module resolution.",
	"database_table_risk": "Database table naming and submitted document links must not be transformed blindly.",
}

CANONICAL_SIDEBAR_ORDER = [
	"Executive Dashboard",
	"Dashboards",
	"Veterinary Records",
	"Hospitalisation",
	"Pet Grooming",
	"Pet Boarding",
	"Veterinary Masters",
	"Reports",
	"Billing",
	"Setup",
]


@dataclass
class Sample:
	file: str
	line: int
	text: str


@dataclass
class ReplacementRule:
	name: str
	description: str
	suffixes: set[str] | None = None
	path_patterns: tuple[str, ...] = ()
	pattern: re.Pattern[str] = field(default_factory=lambda: re.compile(r"$^"))
	replacement: str = ""

	def applies_to(self, relative_path: str, suffix: str) -> bool:
		if self.suffixes is not None and suffix not in self.suffixes:
			return False
		if self.path_patterns and not any(re.search(pattern, relative_path) for pattern in self.path_patterns):
			return False
		return True


@dataclass
class RuleReport:
	rule: str
	description: str
	count: int = 0
	files: set[str] = field(default_factory=set)
	samples: list[Sample] = field(default_factory=list)


@dataclass
class ReferenceRule:
	layer: str
	category: str
	description: str
	pattern: re.Pattern[str]
	path_patterns: tuple[str, ...] = ()

	def applies_to(self, relative_path: str, line: str) -> bool:
		if self.path_patterns and not any(re.search(pattern, relative_path) for pattern in self.path_patterns):
			return False
		return bool(self.pattern.search(line))


def load_reviewed_registry(path: Path = DEFAULT_REGISTRY_PATH) -> dict:
	registry = dict(CLONE_AUDIT_REGISTRY)
	registry["unknown_threshold"] = 0
	registry["classifications"] = []
	if not path.exists():
		return registry

	external = json.loads(path.read_text(encoding="utf-8"))
	for key, value in external.items():
		registry[key] = value
	if "generated_cache_build_exclusions" not in registry:
		registry["generated_cache_build_exclusions"] = sorted(EXCLUDED_DIRS | EXCLUDED_SUFFIXES)
	return registry


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(
		description="Dry-run-only audit for future VetEdge -> Veterinary clone generation."
	)
	parser.add_argument("--source-dir", default=".", help="VetEdge source app directory.")
	parser.add_argument("--output-dir", default="../veterinary", help="Future clone output directory.")
	parser.add_argument("--verbose", action="store_true", help="Print detailed samples and warnings.")
	parser.add_argument("--report-json", help="Optional JSON report path.")
	parser.add_argument("--allow-overwrite", action="store_true", help="Parsed for future phases; no writes in Phase 2A.")
	parser.add_argument("--write", action="store_true", help="Intentionally disabled in Phase 2A.")
	args = parser.parse_args()
	if args.write:
		parser.error(WRITE_DISABLED_MESSAGE)
	return args


def should_skip(path: Path, source_dir: Path) -> tuple[bool, str | None]:
	relative_parts = path.relative_to(source_dir).parts
	for part in relative_parts:
		if part in EXCLUDED_DIRS:
			return True, f"excluded directory: {part}"
	if path.is_file() and path.suffix.lower() in EXCLUDED_SUFFIXES:
		return True, f"excluded suffix: {path.suffix}"
	if path.name.endswith(":Zone.Identifier"):
		return True, "generated Windows metadata stream"
	return False, None


def build_inventory(source_dir: Path) -> tuple[list[Path], list[dict]]:
	files: list[Path] = []
	skipped: list[dict] = []
	for path in sorted(source_dir.rglob("*")):
		skip, reason = should_skip(path, source_dir)
		if skip:
			if path.is_file():
				skipped.append({"path": str(path.relative_to(source_dir)), "reason": reason})
			continue
		if path.is_file():
			files.append(path)
	return files, skipped


def is_text_file(path: Path) -> bool:
	return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"AGENTS.md", "README.md", "patches.txt"}


def read_text(path: Path) -> str | None:
	try:
		return path.read_text(encoding="utf-8")
	except UnicodeDecodeError:
		return None


def line_number_for_offset(text: str, offset: int) -> int:
	return text.count("\n", 0, offset) + 1


def line_text(text: str, line_number: int) -> str:
	lines = text.splitlines()
	if 1 <= line_number <= len(lines):
		return lines[line_number - 1].strip()
	return ""


def replacement_rules() -> list[ReplacementRule]:
	return [
		ReplacementRule(
			name="pyproject_project_name",
			description='pyproject.toml project.name "vetedge" -> "veterinary"',
			path_patterns=(r"^pyproject\.toml$",),
			pattern=re.compile(r'(?m)^name\s*=\s*"vetedge"$'),
			replacement='name = "veterinary"',
		),
		ReplacementRule(
			name="hooks_app_identity",
			description="hooks.py app_name/app_title/app metadata and app_home identity",
			path_patterns=(r"^vetedge/hooks\.py$",),
			pattern=re.compile(
				r'(?m)^(app_name\s*=\s*)"vetedge"|^(app_title\s*=\s*)"VetEdge"|/assets/vetedge/|/desk/vetedge-executive-dashboard'
			),
			replacement="[controlled hooks identity replacement]",
		),
		ReplacementRule(
			name="python_dotted_imports",
			description="Python dotted package references vetedge.* -> veterinary.*",
			suffixes={".py"},
			pattern=re.compile(r"(?<![A-Za-z0-9_])vetedge(?=\.)"),
			replacement="veterinary",
		),
		ReplacementRule(
			name="js_frappe_method_strings",
			description="JS/HTML frappe method strings vetedge.* -> veterinary.*",
			suffixes={".js", ".html"},
			pattern=re.compile(r'(?<=["\'])vetedge(?=\.services\.|\.setup\.|\.install\.|\.coreedge_adapter\.)'),
			replacement="veterinary",
		),
		ReplacementRule(
			name="asset_urls",
			description="/assets/vetedge/... -> /assets/veterinary/...",
			suffixes={".py", ".js", ".json", ".html", ".css", ".md"},
			pattern=re.compile(r"/assets/vetedge/"),
			replacement="/assets/veterinary/",
		),
		ReplacementRule(
			name="executive_dashboard_route",
			description="vetedge-executive-dashboard route -> veterinary-executive-dashboard",
			suffixes={".py", ".js", ".json", ".html"},
			pattern=re.compile(r"\bvetedge-executive-dashboard\b"),
			replacement="veterinary-executive-dashboard",
		),
		ReplacementRule(
			name="uppercase_constants",
			description="Safe uppercase token VETEDGE -> VETERINARY",
			suffixes={".py", ".js", ".json", ".toml", ".md"},
			pattern=re.compile(r"\bVETEDGE\b"),
			replacement="VETERINARY",
		),
		ReplacementRule(
			name="package_path_literals",
			description="Source path literals vetedge/... -> veterinary/...",
			suffixes={".py", ".js", ".json", ".html", ".md", ".toml", ".txt"},
			pattern=re.compile(r"(?<![A-Za-z0-9_])vetedge/"),
			replacement="veterinary/",
		),
	]


def preview_path_renames(files: Iterable[Path], source_dir: Path, output_dir: Path) -> list[dict]:
	renames = []
	for path in files:
		relative = path.relative_to(source_dir)
		parts = list(relative.parts)
		new_parts = parts[:]
		if new_parts and new_parts[0] == "vetedge":
			new_parts[0] = "veterinary"
		if new_parts[-2:] == ["desktop_icon", "vetedge.json"]:
			new_parts[-1] = "veterinary.json"
		if new_parts[-2:] == ["workspace_sidebar", "vetedge.json"]:
			new_parts[-1] = "veterinary.json"
		new_relative = Path(*new_parts)
		if new_relative != relative:
			renames.append(
				{
					"source": str(relative),
					"target": str(output_dir / new_relative),
					"relative_target": str(new_relative),
				}
			)
	return renames


def preview_text_replacements(files: Iterable[Path], source_dir: Path) -> dict[str, RuleReport]:
	reports = {
		rule.name: RuleReport(rule=rule.name, description=rule.description)
		for rule in replacement_rules()
	}
	for path in files:
		if not is_text_file(path):
			continue
		text = read_text(path)
		if text is None:
			continue
		relative = str(path.relative_to(source_dir))
		for rule in replacement_rules():
			if not rule.applies_to(relative, path.suffix.lower()):
				continue
			matches = list(rule.pattern.finditer(text))
			if not matches:
				continue
			report = reports[rule.name]
			report.count += len(matches)
			report.files.add(relative)
			for match in matches[:5]:
				line = line_number_for_offset(text, match.start())
				if len(report.samples) < 12:
					report.samples.append(Sample(file=relative, line=line, text=line_text(text, line)))
	return reports


def reference_rules() -> list[ReferenceRule]:
	return [
		ReferenceRule(
			layer="dangerous",
			category="patch_lineage",
			description=DANGEROUS_REFERENCE_REGISTRY["patch_lineage"],
			path_patterns=(r"^vetedge/patches\.txt$", r"^vetedge/patches/", r"^patches\.txt$", r"^patches/"),
			pattern=re.compile(r".+"),
		),
		ReferenceRule(
			layer="dangerous",
			category="email_template_identity",
			description=DANGEROUS_REFERENCE_REGISTRY["email_template_identity"],
			path_patterns=(r"fixtures/.*email.*template.*\.json$", r"vetedge/setup/email_templates\.py$"),
			pattern=re.compile(r"vetedge|VetEdge|VETEDGE|Powered by VetEdge"),
		),
		ReferenceRule(
			layer="dangerous",
			category="fixture_record_identity",
			description=DANGEROUS_REFERENCE_REGISTRY["fixture_record_identity"],
			path_patterns=(r"^fixtures/", r"/fixtures/"),
			pattern=re.compile(r"vetedge|VetEdge|VETEDGE"),
		),
		ReferenceRule(
			layer="dangerous",
			category="doctype_json_identity",
			description=DANGEROUS_REFERENCE_REGISTRY["doctype_json_identity"],
			path_patterns=(r"/doctype/.+\.json$",),
			pattern=re.compile(r'"(name|doctype|module|autoname|fieldname|options)"|vetedge|VetEdge|VETEDGE'),
		),
		ReferenceRule(
			layer="dangerous",
			category="report_json_identity",
			description=DANGEROUS_REFERENCE_REGISTRY["report_json_identity"],
			path_patterns=(r"/report/.+\.json$",),
			pattern=re.compile(r'"(name|report_name|module|ref_doctype|report_type)"|vetedge|VetEdge|VETEDGE'),
		),
		ReferenceRule(
			layer="dangerous",
			category="scheduler_event_dotted_path",
			description=DANGEROUS_REFERENCE_REGISTRY["scheduler_event_dotted_path"],
			path_patterns=(r"^vetedge/hooks\.py$", r"^hooks\.py$"),
			pattern=re.compile(r'"vetedge\.services\..+"|scheduler_events'),
		),
		ReferenceRule(
			layer="dangerous",
			category="doc_event_dotted_path",
			description=DANGEROUS_REFERENCE_REGISTRY["doc_event_dotted_path"],
			path_patterns=(r"^vetedge/hooks\.py$", r"^hooks\.py$"),
			pattern=re.compile(r'"vetedge\.services\..+"|doc_events'),
		),
		ReferenceRule(
			layer="dangerous",
			category="whitelisted_method_reference",
			description=DANGEROUS_REFERENCE_REGISTRY["whitelisted_method_reference"],
			pattern=re.compile(r"frappe\.call|method:\s*[\"']vetedge\.|frappe\.xcall\([\"']vetedge\."),
		),
		ReferenceRule(
			layer="dangerous",
			category="portal_route",
			description=DANGEROUS_REFERENCE_REGISTRY["portal_route"],
			pattern=re.compile(r"(?<![A-Za-z0-9_/.-])/(?:vetedge_portal|vetedge_guest_booking|vetedge_[A-Za-z0-9_/.-]+)"),
		),
		ReferenceRule(
			layer="dangerous",
			category="coreedge_reference",
			description=DANGEROUS_REFERENCE_REGISTRY["coreedge_reference"],
			path_patterns=(r"coreedge_adapter\.py$", r"test_coreedge_adapter\.py$", r"platform_access\.py$"),
			pattern=re.compile(r"CoreEdge|coreedge|edge_platform|product_app|distribution|VetEdge|vetedge"),
		),
		ReferenceRule(
			layer="dangerous",
			category="desk_route",
			description=DANGEROUS_REFERENCE_REGISTRY["desk_route"],
			pattern=re.compile(r"/desk/[A-Za-z0-9_-]+|vetedge-executive-dashboard"),
		),
		ReferenceRule(
			layer="dangerous",
			category="database_table_risk",
			description=DANGEROUS_REFERENCE_REGISTRY["database_table_risk"],
			pattern=re.compile(r"`tabVetEdge|tabVetEdge"),
		),
		ReferenceRule(
			layer="manual_review",
			category="role_name",
			description=DANGEROUS_REFERENCE_REGISTRY["role_name"],
			pattern=re.compile(r"\bVetEdge (Administrator|Doctor|Front Desk|Groomer|Nurse|Branch Manager|Portal User)\b"),
		),
		ReferenceRule(
			layer="preserve",
			category="protected_clinical_domain_name",
			description="Protected clinical/domain labels must remain unchanged in both apps.",
			pattern=re.compile("|".join(re.escape(term) for term in sorted(PROTECTED_TERMS, key=len, reverse=True))),
		),
		ReferenceRule(
			layer="preserve",
			category="allowed_generic_veterinary_label",
			description="Generic Veterinary labels are intentionally shared by VetEdge and Veterinary.",
			pattern=re.compile(
				"|".join(
					re.escape(term)
					for term in sorted(CLONE_AUDIT_REGISTRY["allowed_generic_veterinary_labels"], key=len, reverse=True)
				)
			),
		),
	]


def registry_reference_rules(registry: dict) -> list[ReferenceRule]:
	rules = []
	for item in registry.get("classifications") or []:
		try:
			rules.append(
				ReferenceRule(
					layer=item["layer"],
					category=item["category"],
					description=item["description"],
					path_patterns=tuple(item.get("path_patterns") or ()),
					pattern=re.compile(item["pattern"]),
				)
			)
		except KeyError as exc:
			raise ValueError(f"Invalid clone audit registry classification missing {exc}") from exc
	return rules


def safe_transform_rule_for_line(relative: str, suffix: str, line: str) -> str | None:
	for rule in replacement_rules():
		if rule.applies_to(relative, suffix) and rule.pattern.search(line):
			return rule.name
	return None


def classify_line(relative: str, suffix: str, line: str, registry: dict | None = None) -> tuple[str, str, str]:
	"""Classify a reference line into the Phase 2B review layers.

	Dangerous rules intentionally win over safe-transform matches. For example,
	a patch file may contain a dotted import that is syntactically transformable,
	but patch lineage still needs human review before any write phase.
	"""
	for layer in ("dangerous", "manual_review", "preserve"):
		for rule in reference_rules():
			if rule.layer == layer and rule.applies_to(relative, line):
				return rule.layer, rule.category, rule.description

	if registry:
		for layer in ("dangerous", "manual_review", "preserve", "safe_transform"):
			for rule in registry_reference_rules(registry):
				if rule.layer == layer and rule.applies_to(relative, line):
					return rule.layer, rule.category, rule.description

	safe_rule = safe_transform_rule_for_line(relative, suffix, line)
	if safe_rule:
		return "safe_transform", safe_rule, "Line matches a controlled transformation preview rule."

	return "unknown", "unclassified_reference", "No reviewed registry rule matched this reference."


def classify_remaining_references(
	files: Iterable[Path],
	source_dir: Path,
	registry: dict | None = None,
) -> dict[str, list[dict]]:
	classified = {layer: [] for layer in ("safe_transform", "preserve", "manual_review", "dangerous", "unknown")}
	pattern = re.compile(r"vetedge|VetEdge|VETEDGE|Veterinary|Stock Expiry Status")
	for path in files:
		if not is_text_file(path):
			continue
		text = read_text(path)
		if text is None or not pattern.search(text):
			continue
		relative = str(path.relative_to(source_dir))
		for line_no, line in enumerate(text.splitlines(), start=1):
			if not pattern.search(line):
				continue
			layer, category, description = classify_line(relative, path.suffix.lower(), line, registry)
			item = {
				"file": relative,
				"line": line_no,
				"text": line.strip(),
				"layer": layer,
				"category": category,
				"description": description,
			}
			classified[layer].append(item)
	return classified


def collect_manual_review_references(files: Iterable[Path], source_dir: Path) -> dict[str, list[dict]]:
	checks = {
		"routes": re.compile(r"(/desk/[A-Za-z0-9_-]+|[A-Za-z0-9_-]+-dashboard|/vetedge_[A-Za-z0-9_/.-]+)"),
		"assets": re.compile(r"/assets/vetedge/[A-Za-z0-9_/.-]+"),
		"methods": re.compile(r"vetedge\.[A-Za-z0-9_.]+"),
	}
	result = {name: [] for name in checks}
	for path in files:
		if not is_text_file(path):
			continue
		text = read_text(path)
		if text is None:
			continue
		relative = str(path.relative_to(source_dir))
		for line_no, line in enumerate(text.splitlines(), start=1):
			for name, pattern in checks.items():
				if pattern.search(line):
					result[name].append({"file": relative, "line": line_no, "text": line.strip()})
	return result


def load_sidebar(source_dir: Path) -> dict | None:
	sidebar_path = source_dir / "vetedge" / "workspace_sidebar" / "vetedge.json"
	if not sidebar_path.exists():
		return None
	try:
		return json.loads(sidebar_path.read_text(encoding="utf-8"))
	except Exception:
		return None


def sidebar_items(sidebar: dict | None) -> list[dict]:
	if not sidebar:
		return []
	items = sidebar.get("items")
	if isinstance(items, list):
		return items
	return []


def verify_sidebar(source_dir: Path) -> dict:
	items = sidebar_items(load_sidebar(source_dir))
	top_level = [
		item.get("label")
		for item in items
		if item.get("type") == "Section Break" or not bool(item.get("child"))
	]
	links = [item for item in items if item.get("type") != "Section Break"]
	return {
		"canonical_order_detected": top_level[: len(CANONICAL_SIDEBAR_ORDER)] == CANONICAL_SIDEBAR_ORDER,
		"detected_order": top_level[: len(CANONICAL_SIDEBAR_ORDER)],
		"veterinary_patient_under_veterinary_records": link_under_section(
			items, "Veterinary Records", "Veterinary Patient", "DocType", link_to="Veterinary Patient"
		),
		"stock_expiry_status_report_linked": any(
			item.get("label") == "Stock Expiry Status"
			and item.get("link_to") == "Stock Expiry Status"
			and item.get("link_type") == "Report"
			for item in links
		),
		"financial_dashboard_under_dashboards": link_under_section(
			items, "Dashboards", "Financial Dashboard", "Page"
		),
		"hospitalisation_dashboard_under_hospitalisation": link_under_section(
			items, "Hospitalisation", "Hospitalisation Dashboard", "Page"
		),
	}


def link_under_section(
	items: list[dict],
	section_label: str,
	link_label: str,
	link_type: str,
	link_to: str | None = None,
) -> bool:
	current_section = None
	for item in items:
		if item.get("type") == "Section Break":
			current_section = item.get("label")
			continue
		if (
			current_section == section_label
			and (item.get("label") == link_label or (link_to is not None and item.get("link_to") == link_to))
			and item.get("link_type") == link_type
		):
			return True
	return False


def verify_dashboard_shell(source_dir: Path) -> dict:
	path = source_dir / "vetedge" / "public" / "js" / "dashboard_shell.js"
	if not path.exists():
		return {"exists": False, "fallback_present": False}
	text = read_text(path) or ""
	return {
		"exists": True,
		"fallback_present": all(
			token in text
			for token in (
				"renderChartTable",
				"chart.empty_state",
				"chart.rows",
				"!frappe.Chart",
				"VetEdge dashboard chart failed to render",
			)
		),
	}


def warn_static_risks(files: Iterable[Path], source_dir: Path) -> list[dict]:
	warnings: list[dict] = []
	for path in files:
		relative = str(path.relative_to(source_dir))
		if relative == "vetedge/patches.txt" or relative.startswith("vetedge/patches/"):
			warnings.append({"file": relative, "category": "patch_lineage", "message": "Patch history must not be blindly renamed."})
		elif "/doctype/" in relative and relative.endswith(".json"):
			warnings.append({"file": relative, "category": "doctype_json", "message": "DocType names and table names are link-sensitive."})
		elif "/report/" in relative and relative.endswith(".json"):
			warnings.append({"file": relative, "category": "report_json", "message": "Report record names and module paths need review."})
		elif relative.startswith("fixtures/") or "/fixtures/" in relative:
			warnings.append({"file": relative, "category": "fixture_record", "message": "Fixture record names may be live identifiers."})
		elif relative == "vetedge/coreedge_adapter.py":
			warnings.append({"file": relative, "category": "coreedge_reference", "message": "CoreEdge product/distribution semantics need explicit support."})
	return warnings


def reference_category_counts(classified: dict[str, list[dict]]) -> dict[str, dict[str, int]]:
	counts: dict[str, dict[str, int]] = {}
	for layer, items in classified.items():
		layer_counts: dict[str, int] = {}
		for item in items:
			category = item.get("category") or "uncategorized"
			layer_counts[category] = layer_counts.get(category, 0) + 1
		counts[layer] = dict(sorted(layer_counts.items()))
	return counts


def reference_layer_counts(classified: dict[str, list[dict]]) -> dict[str, int]:
	return {layer: len(items) for layer, items in classified.items()}


def audit_status(classified: dict[str, list[dict]], registry: dict) -> dict:
	unknown_count = len(classified.get("unknown") or [])
	threshold = int(registry.get("unknown_threshold") or 0)
	return {
		"unknown_threshold": threshold,
		"unknown_count": unknown_count,
		"unknown_within_threshold": unknown_count <= threshold,
		"failure_reason": None
		if unknown_count <= threshold
		else f"Unknown references exceed approved threshold: {unknown_count} > {threshold}",
	}


def report_to_jsonable(report: dict) -> dict:
	def convert(value):
		if isinstance(value, RuleReport):
			return {
				"rule": value.rule,
				"description": value.description,
				"count": value.count,
				"files": sorted(value.files),
				"samples": [sample.__dict__ for sample in value.samples],
			}
		if isinstance(value, dict):
			return {key: convert(val) for key, val in value.items()}
		if isinstance(value, list):
			return [convert(item) for item in value]
		if isinstance(value, set):
			return sorted(value)
		return value

	return convert(report)


def print_summary(report: dict, verbose: bool) -> None:
	print("VetEdge -> Veterinary clone audit dry run")
	print(f"Phase: {report['phase']} audit-only")
	print(f"Source: {report['source_dir']}")
	print(f"Output preview: {report['output_dir']}")
	print(f"Files inventoried: {report['inventory']['files_count']}")
	print(f"Files skipped: {len(report['inventory']['skipped'])}")
	print(f"Planned path renames: {len(report['path_renames'])}")
	print("Planned replacements by rule:")
	for item in report_to_jsonable(report)["text_replacements"].values():
		if item["count"]:
			print(f"  - {item['rule']}: {item['count']} matches in {len(item['files'])} files")
	layer_counts = report["reference_layer_counts"]
	category_counts = report["reference_category_counts"]
	print("Reference layer counts:")
	for layer in ("safe_transform", "preserve", "manual_review", "dangerous", "unknown"):
		print(f"  - {layer}: {layer_counts.get(layer, 0)}")
	print("Reference category counts:")
	for layer in ("safe_transform", "preserve", "manual_review", "dangerous", "unknown"):
		layer_categories = category_counts.get(layer) or {}
		if not layer_categories:
			continue
		print(f"  {layer}:")
		for category, count in layer_categories.items():
			print(f"    - {category}: {count}")
	print("Static checks:")
	for key, value in report["static_checks"]["sidebar"].items():
		print(f"  - {key}: {value}")
	for key, value in report["static_checks"]["dashboard_shell"].items():
		print(f"  - dashboard_shell_{key}: {value}")
	status = report["audit_status"]
	print(
		f"Unknown threshold: {status['unknown_count']} / {status['unknown_threshold']} "
		f"(within threshold: {status['unknown_within_threshold']})"
	)
	if status["failure_reason"]:
		print(f"Audit failure: {status['failure_reason']}")
	if verbose:
		for layer, title in (
			("manual_review", "Top manual review references"),
			("dangerous", "Top dangerous references"),
			("unknown", "Top unknown references"),
		):
			print(f"\n{title}:")
			for item in report["remaining_references"][layer][:20]:
				print(f"  - {item['category']}: {item['file']}:{item['line']} {item['text']}")
		print("\nPath rename preview:")
		for item in report["path_renames"][:25]:
			print(f"  - {item['source']} -> {item['relative_target']}")


def build_audit_report(source_dir: Path, output_dir: Path, registry: dict | None = None) -> dict:
	files, skipped = build_inventory(source_dir)
	registry = registry or load_reviewed_registry()
	text_replacements = preview_text_replacements(files, source_dir)
	remaining_references = classify_remaining_references(files, source_dir, registry)
	status = audit_status(remaining_references, registry)
	return {
		"phase": "2C",
		"mode": "dry-run-only",
		"write_disabled_message": WRITE_DISABLED_MESSAGE,
		"source_dir": str(source_dir),
		"output_dir": str(output_dir),
		"inventory": {
			"files_count": len(files),
			"text_files_count": sum(1 for path in files if is_text_file(path)),
			"skipped": skipped,
		},
		"path_renames": preview_path_renames(files, source_dir, output_dir),
		"text_replacements": text_replacements,
		"registry": registry,
		"dangerous_reference_registry": DANGEROUS_REFERENCE_REGISTRY,
		"protected_terms": sorted(registry.get("protected_clinical_domain_names") or PROTECTED_TERMS),
		"remaining_references": remaining_references,
		"reference_layer_counts": reference_layer_counts(remaining_references),
		"reference_category_counts": reference_category_counts(remaining_references),
		"audit_status": status,
		"manual_review_references": collect_manual_review_references(files, source_dir),
		"dangerous_reference_warnings": warn_static_risks(files, source_dir),
		"static_checks": {
			"sidebar": verify_sidebar(source_dir),
			"dashboard_shell": verify_dashboard_shell(source_dir),
		},
	}


def main() -> int:
	args = parse_args()
	source_dir = Path(args.source_dir).resolve()
	output_dir = Path(args.output_dir).resolve()
	if not source_dir.exists():
		print(f"Source directory does not exist: {source_dir}", file=sys.stderr)
		return 2

	report = build_audit_report(source_dir, output_dir)
	report["allow_overwrite_requested"] = bool(args.allow_overwrite)

	print_summary(report, args.verbose)

	if args.report_json:
		report_path = Path(args.report_json)
		report_path.parent.mkdir(parents=True, exist_ok=True)
		report_path.write_text(json.dumps(report_to_jsonable(report), indent=2, sort_keys=True), encoding="utf-8")
		print(f"JSON report written: {report_path}")

	return 0 if report["audit_status"]["unknown_within_threshold"] else 1


if __name__ == "__main__":
	raise SystemExit(main())
