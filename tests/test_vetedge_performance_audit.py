from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_performance_audit.py"


def load_audit_tool():
	spec = importlib.util.spec_from_file_location("vetedge_performance_audit", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


class VetEdgePerformanceAuditTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_audit_tool()

	def test_audit_detects_speed_and_data_usage_review_signals(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			root = Path(temp_dir)
			self.write(
				root / "vetedge" / "veterinary" / "page" / "demo" / "demo.js",
				"""
frappe.pages.demo.on_page_show = function(wrapper) {
    if (wrapper.vue_app) wrapper.vue_app.unmount();
    frappe.require('edgeui.bundle.js', () => frappe.call('demo.method'));
    setInterval(() => frappe.call('demo.refresh'), 5000);
};
""",
			)
			self.write(
				root / "vetedge" / "services" / "demo.py",
				"""
import frappe

def load_everything():
    return frappe.get_all('Veterinary Patient', fields=['name'])

def load_large_page():
    return frappe.get_list('Veterinary Consultation', fields=['name'], page_length=250)
""",
			)
			bundle = root / "vetedge" / "public" / "js" / "heavy.bundle.js"
			bundle.parent.mkdir(parents=True, exist_ok=True)
			bundle.write_text("x" * 4096, encoding="utf-8")

			report = self.tool.audit_repository(
				root,
				self.tool.AuditConfig(
					bundle_warning_kb=1,
					bundle_high_kb=3,
					large_source_warning_kb=1,
					page_length_warning=100,
				),
			)

			categories = {finding["category"] for finding in report["findings"]}
			self.assertIn("polling", categories)
			self.assertIn("page_remount", categories)
			self.assertIn("unbounded_query", categories)
			self.assertIn("large_query_page", categories)
			self.assertIn("bundle_size", categories)
			self.assertEqual(report["frontend_frappe_call_occurrences"], 2)
			self.assertEqual(report["edgesuite_loader_files"], 1)
			self.assertGreaterEqual(report["severity_counts"]["high"], 1)

	def test_explicitly_bounded_get_all_is_not_reported_as_unbounded(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			root = Path(temp_dir)
			self.write(
				root / "vetedge" / "services" / "bounded.py",
				"""
import frappe

def load_page():
    return frappe.get_all('Veterinary Patient', fields=['name'], limit=20)
""",
			)

			report = self.tool.audit_repository(root)

			self.assertFalse(any(item["category"] == "unbounded_query" for item in report["findings"]))

	def test_markdown_renders_review_warning_and_live_baseline(self):
		report = {
			"files_scanned": 1,
			"bytes_scanned": 100,
			"frontend_frappe_call_occurrences": 2,
			"edgesuite_loader_files": 1,
			"severity_counts": {"high": 0, "medium": 1, "low": 0, "info": 0},
			"findings": [
				{
					"severity": "medium",
					"category": "page_remount",
					"path": "demo.js",
					"line": 4,
					"message": "Review remount behaviour.",
					"metric": None,
				}
			],
		}

		markdown = self.tool.render_markdown(report)

		self.assertIn("Read-only static baseline", markdown)
		self.assertIn("page_remount", markdown)
		self.assertIn("Required live baseline", markdown)

	def test_cli_creates_json_and_markdown_without_mutating_source(self):
		with tempfile.TemporaryDirectory() as temp_dir:
			root = Path(temp_dir) / "repo"
			self.write(root / "vetedge" / "services" / "safe.py", "VALUE = 1\n")
			before = (root / "vetedge" / "services" / "safe.py").read_text(encoding="utf-8")
			json_out = Path(temp_dir) / "audit.json"
			markdown_out = Path(temp_dir) / "audit.md"

			result = subprocess.run(
				[
					sys.executable,
					str(SCRIPT_PATH),
					"--root",
					str(root),
					"--json-out",
					str(json_out),
					"--markdown-out",
					str(markdown_out),
				],
				check=False,
				capture_output=True,
				text=True,
			)

			self.assertEqual(result.returncode, 0, result.stderr)
			self.assertTrue(json_out.exists())
			self.assertTrue(markdown_out.exists())
			self.assertEqual(
				(root / "vetedge" / "services" / "safe.py").read_text(encoding="utf-8"),
				before,
			)

	@staticmethod
	def write(path: Path, content: str) -> None:
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
	unittest.main()
