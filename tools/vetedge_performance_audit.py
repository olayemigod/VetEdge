from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


TEXT_EXTENSIONS = {".py", ".js", ".vue", ".css", ".json", ".html"}
EXCLUDED_PARTS = {".git", "node_modules", "__pycache__", ".venv", "env", "dist"}
SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3}


@dataclass(frozen=True)
class Finding:
	severity: str
	category: str
	path: str
	message: str
	line: int | None = None
	metric: int | float | None = None


@dataclass(frozen=True)
class AuditConfig:
	bundle_warning_kb: int = 350
	bundle_high_kb: int = 750
	large_source_warning_kb: int = 180
	page_length_warning: int = 100


def _repo_relative(path: Path, root: Path) -> str:
	try:
		return path.resolve().relative_to(root.resolve()).as_posix()
	except ValueError:
		return path.as_posix()


def iter_source_files(root: Path) -> Iterable[Path]:
	for path in root.rglob("*"):
		if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
			continue
		if any(part in EXCLUDED_PARTS for part in path.parts):
			continue
		yield path


def _line_number(text: str, needle: str) -> int | None:
	index = text.find(needle)
	if index < 0:
		return None
	return text.count("\n", 0, index) + 1


def _call_name(node: ast.AST) -> str:
	parts: list[str] = []
	current = node
	while isinstance(current, ast.Attribute):
		parts.append(current.attr)
		current = current.value
	if isinstance(current, ast.Name):
		parts.append(current.id)
	return ".".join(reversed(parts))


def _constant_number(node: ast.AST | None) -> int | float | None:
	if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
		return node.value
	return None


def scan_python(path: Path, root: Path, text: str, config: AuditConfig) -> list[Finding]:
	findings: list[Finding] = []
	relative = _repo_relative(path, root)
	try:
		tree = ast.parse(text, filename=str(path))
	except SyntaxError as error:
		return [
			Finding(
				"medium",
				"audit_parse",
				relative,
				f"Python source could not be parsed by the performance audit: {error.msg}",
				error.lineno,
			)
		]

	for node in ast.walk(tree):
		if not isinstance(node, ast.Call):
			continue
		name = _call_name(node.func)
		keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}

		if name in {"frappe.get_all", "frappe.db.get_all"}:
			has_limit = any(key in keywords for key in ("limit", "page_length", "limit_page_length"))
			if not has_limit:
				findings.append(
					Finding(
						"medium",
						"unbounded_query",
						relative,
						"frappe.get_all() has no explicit limit. Review whether the result set is naturally bounded by its filters.",
						getattr(node, "lineno", None),
					)
				)

		for key in ("limit", "page_length", "limit_page_length"):
			value = _constant_number(keywords.get(key))
			if value is not None and value > config.page_length_warning:
				findings.append(
					Finding(
						"medium",
						"large_query_page",
						relative,
						f"Query requests {value:g} rows in one call; verify this is necessary for an interactive workflow.",
						getattr(node, "lineno", None),
						value,
					)
				)

	return findings


def scan_frontend(path: Path, root: Path, text: str, config: AuditConfig) -> list[Finding]:
	findings: list[Finding] = []
	relative = _repo_relative(path, root)

	if "setInterval(" in text:
		findings.append(
			Finding(
				"medium",
				"polling",
				relative,
				"setInterval() can create continuous network/data usage. Confirm the interval is essential and pauses when the page is inactive.",
				_line_number(text, "setInterval("),
			)
		)

	if "on_page_show" in text and ".unmount()" in text:
		findings.append(
			Finding(
				"medium",
				"page_remount",
				relative,
				"Page-show unmount/remount can repeat API calls when users return to a Desk page. Review reuse, freshness TTL, or explicit refresh instead.",
				_line_number(text, ".unmount()"),
			)
		)

	for match in re.finditer(r"(?:page_length|limit)\s*:\s*(\d+)", text):
		value = int(match.group(1))
		if value > config.page_length_warning:
			findings.append(
				Finding(
					"medium",
					"large_client_page",
					relative,
					f"Client requests {value} rows in one call; prefer paginated/on-demand loading for routine screens.",
					text.count("\n", 0, match.start()) + 1,
					value,
				)
			)

	return findings


def scan_file_size(path: Path, root: Path, config: AuditConfig) -> list[Finding]:
	relative = _repo_relative(path, root)
	size_bytes = path.stat().st_size
	size_kb = round(size_bytes / 1024, 1)
	findings: list[Finding] = []

	is_public_asset = "/public/" in f"/{relative}" and path.suffix.lower() in {".js", ".css"}
	is_bundle = path.name.endswith(".bundle.js") or path.name.endswith(".bundle.css")
	if is_public_asset and is_bundle and size_kb >= config.bundle_warning_kb:
		severity = "high" if size_kb >= config.bundle_high_kb else "medium"
		findings.append(
			Finding(
				severity,
				"bundle_size",
				relative,
				f"Public bundle source is {size_kb:g} KB. Measure compressed transfer size and split page-specific code where practical.",
				metric=size_kb,
			)
		)
	elif path.suffix.lower() in {".js", ".vue"} and size_kb >= config.large_source_warning_kb:
		findings.append(
			Finding(
				"low",
				"large_frontend_source",
				relative,
				f"Frontend source is {size_kb:g} KB. Review whether the page can defer secondary workflows/components.",
				metric=size_kb,
			)
		)

	return findings


def audit_repository(root: Path, config: AuditConfig | None = None) -> dict:
	root = root.resolve()
	config = config or AuditConfig()
	findings: list[Finding] = []
	files_scanned = 0
	bytes_scanned = 0
	frontend_calls = 0
	edgesuite_loaders = 0

	for path in iter_source_files(root):
		files_scanned += 1
		bytes_scanned += path.stat().st_size
		text = path.read_text(encoding="utf-8", errors="replace")
		findings.extend(scan_file_size(path, root, config))

		if path.suffix.lower() == ".py":
			findings.extend(scan_python(path, root, text, config))
		elif path.suffix.lower() in {".js", ".vue", ".html"}:
			findings.extend(scan_frontend(path, root, text, config))
			frontend_calls += text.count("frappe.call(")
			if "edgeui.bundle.js" in text and "frappe.require(" in text:
				edgesuite_loaders += 1

	findings.sort(
		key=lambda item: (
			-SEVERITY_ORDER.get(item.severity, 0),
			item.category,
			item.path,
			item.line or 0,
		)
	)
	severity_counts = {
		severity: sum(1 for finding in findings if finding.severity == severity)
		for severity in ("high", "medium", "low", "info")
	}
	category_counts: dict[str, int] = {}
	for finding in findings:
		category_counts[finding.category] = category_counts.get(finding.category, 0) + 1

	return {
		"schema_version": 1,
		"mode": "read_only_static_audit",
		"root": str(root),
		"files_scanned": files_scanned,
		"bytes_scanned": bytes_scanned,
		"frontend_frappe_call_occurrences": frontend_calls,
		"edgesuite_loader_files": edgesuite_loaders,
		"severity_counts": severity_counts,
		"category_counts": dict(sorted(category_counts.items())),
		"thresholds": asdict(config),
		"findings": [asdict(finding) for finding in findings],
		"notes": [
			"Static findings are review signals, not proof of a production bottleneck.",
			"Browser Network/Lighthouse measurements and server query profiling remain required before changing business logic or indexes.",
			"This audit performs no writes to the Frappe site, database, or source tree.",
		],
	}


def render_markdown(report: dict) -> str:
	severity = report["severity_counts"]
	lines = [
		"# VetEdge Performance & Data Efficiency Audit",
		"",
		"> Read-only static baseline. Validate findings with browser/network and server profiling before optimisation.",
		"",
		"## Summary",
		"",
		f"- Files scanned: {report['files_scanned']}",
		f"- Source bytes scanned: {report['bytes_scanned']}",
		f"- Frontend `frappe.call` occurrences: {report['frontend_frappe_call_occurrences']}",
		f"- EdgeSuite loader files: {report['edgesuite_loader_files']}",
		f"- Findings: high {severity['high']}, medium {severity['medium']}, low {severity['low']}",
		"",
		"## Findings",
		"",
	]
	if not report["findings"]:
		lines.append("No static findings exceeded the configured thresholds.")
	else:
		for finding in report["findings"]:
			location = finding["path"]
			if finding.get("line"):
				location += f":{finding['line']}"
			lines.append(
				f"- **{finding['severity'].upper()} · {finding['category']}** — `{location}` — {finding['message']}"
			)
	lines.extend(
		[
			"",
			"## Required live baseline",
			"",
			"For each priority workflow capture cold load, warm load and repeat navigation: transferred bytes, request count, largest assets, API duration, payload size, server duration and slow-query evidence.",
		]
	)
	return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Read-only VetEdge performance and data-efficiency static audit.")
	parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]), help="VetEdge repository root.")
	parser.add_argument("--json-out", help="Optional JSON output path.")
	parser.add_argument("--markdown-out", help="Optional Markdown output path.")
	parser.add_argument("--bundle-warning-kb", type=int, default=350)
	parser.add_argument("--bundle-high-kb", type=int, default=750)
	parser.add_argument("--large-source-warning-kb", type=int, default=180)
	parser.add_argument("--page-length-warning", type=int, default=100)
	parser.add_argument("--fail-on-high", action="store_true", help="Return non-zero when high-severity findings exist.")
	return parser.parse_args()


def main() -> int:
	args = parse_args()
	config = AuditConfig(
		bundle_warning_kb=args.bundle_warning_kb,
		bundle_high_kb=args.bundle_high_kb,
		large_source_warning_kb=args.large_source_warning_kb,
		page_length_warning=args.page_length_warning,
	)
	report = audit_repository(Path(args.root), config)
	json_text = json.dumps(report, indent=2, sort_keys=True)
	markdown_text = render_markdown(report)

	if args.json_out:
		Path(args.json_out).write_text(json_text + "\n", encoding="utf-8")
	else:
		print(json_text)
	if args.markdown_out:
		Path(args.markdown_out).write_text(markdown_text, encoding="utf-8")

	if args.fail_on_high and report["severity_counts"]["high"]:
		return 2
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
