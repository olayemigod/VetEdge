from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "vetedge_data_migration_audit.py"


def load_audit_tool():
	spec = importlib.util.spec_from_file_location("vetedge_data_migration_audit", SCRIPT_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec.loader is not None
	sys.modules[spec.name] = module
	spec.loader.exec_module(module)
	return module


class VetEdgeDataMigrationAuditTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.tool = load_audit_tool()

	def test_vetedge_strings_are_detected_in_fields(self):
		findings = self.tool.detect_string_risks(
			"Workspace",
			"VetEdge",
			{
				"name": "VetEdge",
				"route": "/desk/vetedge-executive-dashboard",
				"asset": "/assets/vetedge/js/dashboard_shell.js",
				"method": "vetedge.services.reporting_logic_v4.get_dashboard_payload",
			},
		)
		categories = {finding.category for finding in findings}
		reasons = " ".join(finding.reason for finding in findings)

		self.assertIn(self.tool.CATEGORY_DANGEROUS, categories)
		self.assertIn(self.tool.CATEGORY_MAPPING, categories)
		self.assertIn("desk_route", reasons)
		self.assertIn("dotted_path", reasons)

	def test_submitted_financial_and_stock_documents_are_dangerous(self):
		for doctype in ("Sales Invoice", "Payment Entry", "Stock Entry"):
			_category, findings = self.tool.classify_record(doctype, {"name": f"{doctype}-001", "docstatus": 1})
			self.assertTrue(any(finding.category == self.tool.CATEGORY_DANGEROUS for finding in findings))

	def test_generic_veterinary_clinical_records_are_directly_portable(self):
		category, reason = self.tool.classify_doctype("Veterinary Patient")

		self.assertEqual(category, self.tool.CATEGORY_DIRECT)
		self.assertIn("Generic Veterinary", reason)

	def test_email_templates_with_vetedge_branding_are_manual_review(self):
		category, findings = self.tool.classify_record(
			"Email Template",
			{"name": "VetEdge - Appointment Created", "response": "Powered by VetEdge"},
		)

		self.assertEqual(category, self.tool.CATEGORY_MANUAL)
		self.assertTrue(any(finding.category == self.tool.CATEGORY_MANUAL for finding in findings))

	def test_role_names_with_vetedge_are_manual_review(self):
		category, findings = self.tool.classify_record("Role", {"name": "VetEdge Doctor"})

		self.assertEqual(category, self.tool.CATEGORY_MANUAL)
		self.assertTrue(any("role mapping" in finding.reason for finding in findings))

	def test_portal_routes_with_vetedge_are_dangerous(self):
		findings = self.tool.detect_string_risks("Portal Settings", "Portal Settings", {"route": "/vetedge_guest_booking"})

		self.assertTrue(any(finding.category == self.tool.CATEGORY_DANGEROUS for finding in findings))

	def test_coreedge_activation_references_are_platform_dependent(self):
		category, findings = self.tool.classify_record(
			"CoreEdge Product Activation",
			{"name": "VetEdge Activation", "product_app": "VetEdge", "provider": "coreedge"},
		)

		self.assertEqual(category, self.tool.CATEGORY_PLATFORM)
		self.assertTrue(any(finding.category == self.tool.CATEGORY_PLATFORM for finding in findings))

	def test_export_manifest_has_no_destructive_write_operations(self):
		audits = [
			self.tool.DoctypeAudit("Veterinary Patient", self.tool.CATEGORY_DIRECT, "ok", record_count=3),
			self.tool.DoctypeAudit("Sales Invoice", self.tool.CATEGORY_ERPNEXT, "dependency", record_count=2),
		]

		manifest = self.tool.build_export_manifest(audits)

		self.assertEqual(manifest["mode"], "manifest_only_no_data_export")
		self.assertEqual(manifest["destructive_operations"], [])
		self.assertFalse(any("write" in str(item).lower() for item in manifest["doctypes"]))

	def test_write_mode_fails_intentionally(self):
		result = subprocess.run(
			[
				sys.executable,
				str(SCRIPT_PATH),
				"--site",
				"vetedge.local",
				"--write",
			],
			check=False,
			capture_output=True,
			text=True,
		)

		self.assertNotEqual(result.returncode, 0)
		self.assertIn("write mode intentionally disabled for data migration audit", result.stderr)


if __name__ == "__main__":
	unittest.main()
