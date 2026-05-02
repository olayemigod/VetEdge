from __future__ import annotations

import json
from pathlib import Path
from unittest import TestCase


VETERINARY_ROOT = Path(__file__).resolve().parents[1] / "veterinary"
WORKSPACE_PATH = VETERINARY_ROOT.parent / "workspace_sidebar" / "vetedge.json"
PUBLIC_ROOT = VETERINARY_ROOT.parent / "public" / "js"


EXPECTED_PAGE_ROLES = {
	"page/vetedge_executive_dashboard/vetedge_executive_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
	},
	"page/vetedge_clinical_dashboard/vetedge_clinical_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/veterinary_financial_dashboard/veterinary_financial_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Accounts/Cashier",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/vetedge_inventory_dispensary_dashboard/vetedge_inventory_dispensary_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"VetEdge Dispensary User",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/vetedge_lab_dashboard/vetedge_lab_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"Lab Technician",
		"VetEdge Lab Technician",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/vetedge_vaccination_dashboard/vetedge_vaccination_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/vetedge_boarding_dashboard/vetedge_boarding_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/vetedge_grooming_dashboard/vetedge_grooming_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Groomer",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/vetedge_practitioner_performance_dashboard/vetedge_practitioner_performance_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"page/vetedge_branch_performance_dashboard/vetedge_branch_performance_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
}

EXPECTED_REPORT_ROLES = {
	"report/consultation_register/consultation_register.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/patient_register/patient_register.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/owner_register/owner_register.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/practitioner_performance_report/practitioner_performance_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/branch_performance_report/branch_performance_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/revenue_summary/revenue_summary.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Accounts/Cashier",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/unpaid_invoice_report/unpaid_invoice_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Accounts/Cashier",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/dispensary_activity_report/dispensary_activity_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"VetEdge Dispensary User",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/stock_usage_summary/stock_usage_summary.json": {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"VetEdge Dispensary User",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/lab_order_report/lab_order_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"Lab Technician",
		"VetEdge Lab Technician",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/vaccination_report/vaccination_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Nurse",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/boarding_report/boarding_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/kennel_availability_report/kennel_availability_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
	"report/grooming_report/grooming_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Groomer",
		"Branch Manager",
		"VetEdge Branch Manager",
	},
}

EXPECTED_WORKSPACE_RULE_SNIPPETS = {
	"VetEdge Executive Dashboard": ["VetEdge Administrator", "System Manager"],
	"Financial Dashboard": ["VetEdge Accounts/Cashier", "Accounts/Cashier", "Branch Manager"],
	"Inventory / Dispensary Dashboard": ["VetEdge Dispensary User", "Dispensary User"],
	"Practitioner Performance Dashboard": ["VetEdge Doctor", "VetEdge Branch Manager"],
	"Revenue Summary": ["VetEdge Accounts/Cashier", "Accounts/Cashier"],
	"Unpaid Invoice Report": ["VetEdge Accounts/Cashier", "Accounts/Cashier"],
	"Grooming Report": ["VetEdge Groomer", "VetEdge Front Desk"],
}

REPORT_JS_WITH_DEFAULTS = {
	"report/consultation_register/consultation_register.js": "Consultation Register",
	"report/patient_register/patient_register.js": "Patient Register",
	"report/practitioner_performance_report/practitioner_performance_report.js": "Practitioner Performance Report",
	"report/revenue_summary/revenue_summary.js": "Revenue Summary",
	"report/unpaid_invoice_report/unpaid_invoice_report.js": "Unpaid Invoice Report",
	"report/dispensary_activity_report/dispensary_activity_report.js": "Dispensary Activity Report",
	"report/lab_order_report/lab_order_report.js": "Lab Order Report",
	"report/vaccination_report/vaccination_report.js": "Vaccination Report",
	"report/boarding_report/boarding_report.js": "Boarding Report",
	"report/grooming_report/grooming_report.js": "Grooming Report",
}


class TestReportingVisibilityMatrix(TestCase):
	def test_dashboard_pages_have_expected_roles(self):
		for relative_path, expected_roles in EXPECTED_PAGE_ROLES.items():
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				self.assertEqual({row["role"] for row in data.get("roles", [])}, expected_roles)

	def test_report_role_sets_are_tightened(self):
		for relative_path, expected_roles in EXPECTED_REPORT_ROLES.items():
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				self.assertEqual({row["role"] for row in data.get("roles", [])}, expected_roles)

	def test_workspace_visibility_rules_match_role_model(self):
		data = json.loads(WORKSPACE_PATH.read_text())
		display_rules = {
			item.get("label"): item.get("display_depends_on", "")
			for item in data.get("items", [])
			if item.get("display_depends_on")
		}
		for label, snippets in EXPECTED_WORKSPACE_RULE_SNIPPETS.items():
			with self.subTest(label=label):
				rule = display_rules.get(label, "")
				for snippet in snippets:
					self.assertIn(snippet, rule)

	def test_reports_apply_visibility_default_helper(self):
		for relative_path, report_name in REPORT_JS_WITH_DEFAULTS.items():
			with self.subTest(target=relative_path):
				source = (VETERINARY_ROOT / relative_path).read_text()
				self.assertIn("window.vetedgeReportVisibility?.apply", source)
				self.assertIn(report_name, source)

	def test_shared_assets_include_report_visibility_helper(self):
		hooks_source = (VETERINARY_ROOT.parent / "hooks.py").read_text()
		self.assertIn("/assets/vetedge/js/report_visibility.js", hooks_source)
		dashboard_shell = (PUBLIC_ROOT / "dashboard_shell.js").read_text()
		self.assertIn("window.vetedgeReportVisibility.applyDashboard", dashboard_shell)
