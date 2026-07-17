from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_staging_export_rehearsal.py"


def load_rehearsal_tool():
	spec = importlib.util.spec_from_file_location("vetedge_staging_export_rehearsal", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def fixture_audit() -> dict:
	return {
		"mode": "read_only_data_migration_audit",
		"site": "vetedge.local",
		"category_counts": {},
		"doctypes": [
			{"doctype": "Veterinary Patient", "category": "directly_portable", "record_count": 3},
			{"doctype": "Veterinary Consultation", "category": "directly_portable", "record_count": 2},
			{"doctype": "Patch Log", "category": "dangerous_do_not_auto_migrate", "record_count": 9},
			{"doctype": "Sales Invoice", "category": "erpnext_native_dependency", "record_count": 5},
			{"doctype": "Role", "category": "requires_manual_review", "record_count": 4},
		],
	}


def fixture_package_manifest() -> dict:
	return {
		"mode": "manifest_templates_samples_only",
		"business_row_payload_exported": False,
		"import_behavior_included": False,
	}


class VetEdgeStagingExportRehearsalTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_rehearsal_tool()

	def test_default_mode_exports_no_business_rows(self):
		audit = fixture_audit()
		plan = self.tool.export_plan(audit, include_row_samples=False, sample_limit=2)
		summary = self.tool.build_rehearsal(audit, fixture_package_manifest(), include_row_samples=False, sample_limit=2)

		self.assertEqual(plan["mode"], "manifest_only_no_rows")
		self.assertFalse(plan["include_row_samples"])
		self.assertFalse(summary["business_data_mutated"])
		self.assertFalse(summary["import_behavior_included"])

	def test_include_row_samples_allows_only_directly_portable_doctypes(self):
		plan = self.tool.export_plan(fixture_audit(), include_row_samples=True, sample_limit=2)

		self.assertEqual(plan["allowed_sample_doctypes"], ["Veterinary Consultation", "Veterinary Patient"])
		excluded = {row["doctype"] for row in plan["excluded_doctypes"]}
		self.assertIn("Patch Log", excluded)
		self.assertIn("Sales Invoice", excluded)
		self.assertNotIn("Role", plan["allowed_sample_doctypes"])

	def test_dangerous_doctypes_are_always_excluded(self):
		audit = {
			"doctypes": [
				{"doctype": "Page", "category": "directly_portable"},
				{"doctype": "Workspace", "category": "directly_portable"},
				{"doctype": "GL Entry", "category": "directly_portable"},
			]
		}
		plan = self.tool.export_plan(audit, include_row_samples=True, sample_limit=2)

		self.assertEqual(plan["allowed_sample_doctypes"], [])
		self.assertEqual({row["doctype"] for row in plan["excluded_doctypes"]}, {"GL Entry", "Page", "Workspace"})

	def test_sensitive_fields_are_redacted(self):
		record = {
			"name": "VP-001",
			"patient_name": "Milo",
			"owner_email": "owner@example.com",
			"api_key": "secret",
			"password": "hidden",
			"notes": "private clinical note",
		}
		redacted, report = self.tool.redact_record(record, {"password": "Password"}, redact_sensitive=True)

		self.assertEqual(redacted["name"], "VP-001")
		self.assertEqual(redacted["patient_name"], "Milo")
		self.assertEqual(redacted["owner_email"], "[REDACTED]")
		self.assertEqual(redacted["api_key"], "[REDACTED]")
		self.assertEqual(redacted["password"], "[REDACTED]")
		self.assertEqual(redacted["notes"], "[REDACTED]")
		self.assertEqual(len(report), 4)

	def test_sample_limit_is_enforced_by_sampler_contract(self):
		audit = fixture_audit()
		plan = self.tool.export_plan(audit, include_row_samples=True, sample_limit=1)

		self.assertEqual(plan["sample_limit"], 1)

	def test_output_contains_no_import_files_or_scripts(self):
		with tempfile.TemporaryDirectory() as tempdir:
			output_dir = Path(tempdir) / "out"
			plan = self.tool.export_plan(fixture_audit(), include_row_samples=False, sample_limit=2)
			summary = self.tool.build_rehearsal(fixture_audit(), fixture_package_manifest())
			self.tool.write_outputs(output_dir, summary, plan, [], plan["excluded_doctypes"], [], {})

			files = {path.name for path in output_dir.rglob("*") if path.is_file()}
			self.assertIn("rehearsal_summary.json", files)
			self.assertIn("export_plan.json", files)
			self.assertNotIn("import.py", files)
			self.assertNotIn("restore.sql", files)

	def test_missing_audit_or_package_files_fail_safely(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--audit-json",
				"/tmp/does-not-exist-audit.json",
				"--package-dir",
				"/tmp/does-not-exist-package",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("Required file not found", result.stderr)

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--audit-json",
				"/tmp/does-not-exist-audit.json",
				"--package-dir",
				"/tmp/does-not-exist-package",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for staging export rehearsal", result.stderr)


if __name__ == "__main__":
	unittest.main()
