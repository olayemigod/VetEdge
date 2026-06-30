from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_migration_package.py"


def load_package_tool():
	spec = importlib.util.spec_from_file_location("vetedge_migration_package", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


def fixture_audit() -> dict:
	return {
		"site": "vetedge.local",
		"category_counts": {
			"directly_portable": 1,
			"requires_manual_review": 3,
			"dangerous_do_not_auto_migrate": 1,
			"erpnext_native_dependency": 2,
		},
		"proposed_migration_order": ["ERPNext masters", "Patients/owners"],
		"missing_mapping_requirements": ["company", "branch", "roles"],
		"doctypes": [
			{
				"doctype": "Veterinary Patient",
				"category": "directly_portable",
				"record_count": 5,
				"reason": "Generic Veterinary domain DocType.",
				"findings": [],
			},
			{
				"doctype": "Patch Log",
				"category": "dangerous_do_not_auto_migrate",
				"record_count": 9,
				"reason": "Patch lineage.",
				"findings": [{"reason": "patch"}],
			},
			{
				"doctype": "Sales Invoice",
				"category": "erpnext_native_dependency",
				"record_count": 3,
				"reason": "ERPNext dependency.",
				"findings": [{"reason": "submitted"}],
			},
			{
				"doctype": "Stock Entry",
				"category": "erpnext_native_dependency",
				"record_count": 2,
				"reason": "ERPNext dependency.",
				"findings": [{"reason": "submitted"}],
			},
			{
				"doctype": "Email Template",
				"category": "requires_manual_review",
				"record_count": 4,
				"reason": "Manual review.",
				"findings": [{"reason": "VetEdge branding"}],
			},
			{
				"doctype": "Role",
				"category": "requires_manual_review",
				"record_count": 2,
				"reason": "Role mapping.",
				"findings": [{"reason": "VetEdge role"}],
			},
			{
				"doctype": "Page",
				"category": "requires_manual_review",
				"record_count": 2,
				"reason": "Route review.",
				"findings": [{"reason": "VetEdge route"}],
			},
		],
	}


class VetEdgeMigrationPackageTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_package_tool()

	def test_package_generation_is_read_only_and_deterministic(self):
		with tempfile.TemporaryDirectory() as tempdir:
			root = Path(tempdir)
			audit_path = root / "audit.json"
			manifest_path = root / "export_manifest.json"
			output_dir = root / "package"
			audit_path.write_text(json.dumps(fixture_audit(), sort_keys=True), encoding="utf-8")
			manifest_path.write_text(json.dumps({"mode": "manifest_only_no_data_export"}, sort_keys=True), encoding="utf-8")

			result = subprocess.run(
				[
					sys.executable,
					str(SCRIPT_PATH),
					"--audit-json",
					str(audit_path),
					"--export-manifest",
					str(manifest_path),
					"--output-dir",
					str(output_dir),
				],
				check=False,
				capture_output=True,
				text=True,
			)

			self.assertEqual(result.returncode, 0, result.stderr)
			first_manifest = (output_dir / "manifest.json").read_text(encoding="utf-8")
			first_template = (output_dir / "mappings" / "company_mapping.template.csv").read_text(encoding="utf-8")

			result = subprocess.run(
				[
					sys.executable,
					str(SCRIPT_PATH),
					"--audit-json",
					str(audit_path),
					"--export-manifest",
					str(manifest_path),
					"--output-dir",
					str(output_dir),
				],
				check=False,
				capture_output=True,
				text=True,
			)

			self.assertEqual(result.returncode, 0, result.stderr)
			self.assertEqual(first_manifest, (output_dir / "manifest.json").read_text(encoding="utf-8"))
			self.assertEqual(first_template, (output_dir / "mappings" / "company_mapping.template.csv").read_text(encoding="utf-8"))

			manifest = json.loads(first_manifest)
			self.assertFalse(manifest["business_row_payload_exported"])
			self.assertFalse(manifest["import_behavior_included"])
			self.assertEqual(manifest["destructive_operations"], [])

	def test_package_contains_required_mapping_templates(self):
		with tempfile.TemporaryDirectory() as tempdir:
			output_dir = Path(tempdir) / "package"
			self.tool.write_package(fixture_audit(), {"mode": "manifest_only_no_data_export"}, output_dir)

			for filename in self.tool.MAPPING_TEMPLATE_NAMES:
				path = output_dir / "mappings" / filename
				self.assertTrue(path.exists(), filename)
				with path.open(newline="", encoding="utf-8") as handle:
					reader = csv.reader(handle)
					self.assertEqual(next(reader), self.tool.MAPPING_COLUMNS)

	def test_dangerous_and_dependency_doctypes_are_separated(self):
		with tempfile.TemporaryDirectory() as tempdir:
			output_dir = Path(tempdir) / "package"
			self.tool.write_package(fixture_audit(), None, output_dir)

			direct = json.loads((output_dir / "doctypes" / "directly_portable.json").read_text(encoding="utf-8"))
			dangerous = json.loads((output_dir / "doctypes" / "dangerous_excluded.json").read_text(encoding="utf-8"))
			dependencies = json.loads((output_dir / "doctypes" / "erpnext_native_dependencies.json").read_text(encoding="utf-8"))

			self.assertEqual([row["doctype"] for row in direct], ["Veterinary Patient"])
			self.assertEqual([row["doctype"] for row in dangerous], ["Patch Log"])
			self.assertEqual({row["doctype"] for row in dependencies}, {"Sales Invoice", "Stock Entry"})
			self.assertTrue(all(row["dependency_only"] for row in dependencies))

	def test_readme_warns_against_unsafe_migrations(self):
		with tempfile.TemporaryDirectory() as tempdir:
			output_dir = Path(tempdir) / "package"
			self.tool.write_package(fixture_audit(), None, output_dir)
			readme = (output_dir / "README.md").read_text(encoding="utf-8")

			for token in ("Patch Log", "GL Entry", "Stock Ledger Entry", "DocField", "DocPerm", "Module Def", "Role", "Has Role", "Workspace", "Page"):
				self.assertIn(token, readme)
			self.assertIn("Do not rewrite submitted Sales Invoice", readme)

	def test_samples_are_schema_only(self):
		with tempfile.TemporaryDirectory() as tempdir:
			output_dir = Path(tempdir) / "package"
			self.tool.write_package(fixture_audit(), None, output_dir)
			sample = output_dir / "samples" / "Veterinary Patient.sample.csv"

			lines = sample.read_text(encoding="utf-8").splitlines()
			self.assertEqual(len(lines), 1)
			self.assertIn("patient_name", lines[0])

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--audit-json",
				"/tmp/missing.json",
				"--output-dir",
				"/tmp/vetedge_migration_package",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for migration package planning", result.stderr)


if __name__ == "__main__":
	unittest.main()
