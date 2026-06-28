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
		"Branch Manager",
	},
	"page/veterinary_financial_dashboard/veterinary_financial_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
		"Branch Manager",
	},
	"page/veterinary_hospitalisation_dashboard/veterinary_hospitalisation_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
	},
	"page/vetedge_inventory_dispensary_dashboard/vetedge_inventory_dispensary_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"Branch Manager",
	},
	"page/vetedge_lab_dashboard/vetedge_lab_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Lab Technician",
		"Branch Manager",
	},
	"page/vetedge_vaccination_dashboard/vetedge_vaccination_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"page/vetedge_boarding_dashboard/vetedge_boarding_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
	},
	"page/vetedge_grooming_dashboard/vetedge_grooming_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Groomer",
		"Branch Manager",
	},
	"page/vetedge_practitioner_performance_dashboard/vetedge_practitioner_performance_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Branch Manager",
	},
	"page/vetedge_branch_performance_dashboard/vetedge_branch_performance_dashboard.json": {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
	},
}

EXPECTED_REPORT_ROLES = {
	"report/consultation_register/consultation_register.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Front Desk",
		"Branch Manager",
	},
	"report/planned_treatment/planned_treatment.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Front Desk",
		"Branch Manager",
	},
	"report/patient_register/patient_register.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"VetEdge Front Desk",
		"Branch Manager",
	},
	"report/owner_register/owner_register.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
	},
	"report/practitioner_performance_report/practitioner_performance_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Branch Manager",
	},
	"report/branch_performance_report/branch_performance_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
	},
	"report/branch_performance_summary/branch_performance_summary.json": {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
	},
	"report/revenue_summary/revenue_summary.json": {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
	},
	"report/unpaid_invoice_report/unpaid_invoice_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"Branch Manager",
		"Accounts/Cashier",
		"Accounts Manager",
		"Sales Manager",
	},
	"report/dispensary_activity_report/dispensary_activity_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"Branch Manager",
	},
	"report/stock_usage_summary/stock_usage_summary.json": {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"Branch Manager",
	},
	"report/stock_expiry_status/stock_expiry_status.json": {
		"System Manager",
		"VetEdge Administrator",
		"Dispensary User",
		"Branch Manager",
	},
	"report/lab_order_report/lab_order_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Lab Technician",
		"Branch Manager",
	},
	"report/vaccination_report/vaccination_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Doctor",
		"Veterinary Nurse",
		"Branch Manager",
	},
	"report/boarding_report/boarding_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
	},
	"report/kennel_availability_report/kennel_availability_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"Branch Manager",
	},
	"report/grooming_report/grooming_report.json": {
		"System Manager",
		"VetEdge Administrator",
		"VetEdge Front Desk",
		"VetEdge Groomer",
		"Branch Manager",
	},
}

EXPECTED_REPORT_FILTER_FIELDS = {
	"report/consultation_register/consultation_register.json": {"from_date", "to_date", "branch", "practitioner", "consultation_type", "patient", "owner", "status", "payment_status", "has_follow_up", "has_vaccination", "created_by"},
	"report/planned_treatment/planned_treatment.json": {"from_date", "to_date", "branch", "patient", "owner", "practitioner", "consultation_type", "item", "consultation_status"},
	"report/patient_register/patient_register.json": {"branch", "owner", "species", "registration_status"},
	"report/owner_register/owner_register.json": {"branch", "owner", "outstanding_only"},
	"report/practitioner_performance_report/practitioner_performance_report.json": {"from_date", "to_date", "branch", "practitioner"},
	"report/branch_performance_report/branch_performance_report.json": {"from_date", "to_date", "branch"},
	"report/branch_performance_summary/branch_performance_summary.json": {"from_date", "to_date", "branch", "cost_center", "chart"},
	"report/revenue_summary/revenue_summary.json": {"from_date", "to_date", "branch", "cost_center", "customer", "status", "service_category"},
	"report/unpaid_invoice_report/unpaid_invoice_report.json": {"from_date", "to_date", "branch", "customer", "age_range"},
	"report/dispensary_activity_report/dispensary_activity_report.json": {"from_date", "to_date", "branch", "warehouse", "item"},
	"report/stock_usage_summary/stock_usage_summary.json": {"from_date", "to_date", "branch", "warehouse", "item"},
	"report/stock_expiry_status/stock_expiry_status.json": {"company", "branch", "warehouse", "item_group", "expiry_buckets", "include_zero_qty"},
	"report/lab_order_report/lab_order_report.json": {"from_date", "to_date", "branch", "patient", "practitioner", "status"},
	"report/vaccination_report/vaccination_report.json": {"from_date", "to_date", "branch", "patient", "owner", "vaccine", "practitioner", "status", "due_status"},
	"report/boarding_report/boarding_report.json": {"from_date", "to_date", "branch", "patient", "owner", "kennel", "status"},
	"report/kennel_availability_report/kennel_availability_report.json": {"from_date", "to_date", "branch", "kennel", "status"},
	"report/grooming_report/grooming_report.json": {"from_date", "to_date", "branch", "patient", "owner", "assigned_staff", "status"},
}

EXPECTED_WORKSPACE_RULE_SNIPPETS = {
	"Executive Dashboard": ["VetEdge Administrator", "System Manager"],
	"Financial Dashboard": ["Accounts/Cashier", "Accounts Manager", "Branch Manager"],
	"Hospitalisation Dashboard": ["VetEdge Doctor", "Veterinary Nurse", "Branch Manager"],
	"Inventory / Dispensary Dashboard": ["Dispensary User", "Branch Manager"],
	"Practitioner Performance Dashboard": ["VetEdge Doctor", "Branch Manager"],
	"Revenue Summary": ["Accounts/Cashier", "Accounts Manager"],
	"Unpaid Invoice Report": ["Accounts/Cashier", "Accounts Manager"],
	"Planned Treatment": ["VetEdge Doctor", "Veterinary Nurse", "VetEdge Front Desk"],
	"Grooming Report": ["VetEdge Groomer", "VetEdge Front Desk"],
	"Patients": ["VetEdge Front Desk", "VetEdge Doctor", "Lab Technician"],
	"Consultations": ["VetEdge Front Desk", "VetEdge Doctor", "Dispensary User"],
	"Appointments": ["VetEdge Front Desk", "VetEdge Doctor", "Veterinary Nurse"],
	"Guest Booking Requests": ["VetEdge Front Desk", "VetEdge Doctor", "Branch Manager"],
	"Appointment Queue": ["VetEdge Front Desk", "VetEdge Doctor", "Dispensary User"],
	"Medical History": ["VetEdge Doctor", "Veterinary Nurse", "Branch Manager"],
	"Vital Signs": ["VetEdge Doctor", "Veterinary Nurse", "Branch Manager"],
	"Species": ["VetEdge Front Desk", "VetEdge Doctor", "Veterinary Nurse"],
	"Service Types": ["VetEdge Doctor", "Dispensary User", "Branch Manager"],
	"Vaccines": ["VetEdge Front Desk", "VetEdge Doctor", "Veterinary Nurse"],
	"Sales Invoice": ["VetEdge Front Desk", "VetEdge Doctor", "Accounts/Cashier"],
	"Payment Entry": ["Accounts/Cashier", "Accounts Manager", "Branch Manager"],
	"Cost Center": ["Accounts/Cashier", "Accounts Manager", "Sales Manager"],
	"Item": ["VetEdge Doctor", "Veterinary Nurse", "Dispensary User"],
	"Stock Expiry Status": ["Dispensary User", "Branch Manager"],
	"Branch": ["VetEdge Administrator", "Branch Manager"],
	"License Profile": ["System Manager"],
}

REPORT_JS_WITH_DEFAULTS = {
	"report/branch_performance_summary/branch_performance_summary.js": "Branch Performance Summary",
	"report/consultation_register/consultation_register.js": "Consultation Register",
	"report/planned_treatment/planned_treatment.js": "Planned Treatment",
	"report/owner_register/owner_register.js": "Owner Register",
	"report/patient_register/patient_register.js": "Patient Register",
	"report/practitioner_performance_report/practitioner_performance_report.js": "Practitioner Performance Report",
	"report/revenue_summary/revenue_summary.js": "Revenue Summary",
	"report/unpaid_invoice_report/unpaid_invoice_report.js": "Unpaid Invoice Report",
	"report/dispensary_activity_report/dispensary_activity_report.js": "Dispensary Activity Report",
	"report/stock_expiry_status/stock_expiry_status.js": "Stock Expiry Status",
	"report/lab_order_report/lab_order_report.js": "Lab Order Report",
	"report/vaccination_report/vaccination_report.js": "Vaccination Report",
	"report/boarding_report/boarding_report.js": "Boarding Report",
	"report/grooming_report/grooming_report.js": "Grooming Report",
}

EXPECTED_REPORT_JS_FILTER_FIELDS = {
	"report/branch_performance_summary/branch_performance_summary.js": {"from_date", "to_date", "branch", "cost_center", "chart"},
	"report/consultation_register/consultation_register.js": {"from_date", "to_date", "branch", "practitioner", "consultation_type", "patient", "owner", "status"},
	"report/planned_treatment/planned_treatment.js": {"from_date", "to_date", "branch", "patient", "owner", "practitioner", "consultation_type", "item", "consultation_status"},
	"report/owner_register/owner_register.js": {"branch", "owner", "outstanding_only"},
	"report/patient_register/patient_register.js": {"branch", "species", "owner", "registration_status"},
	"report/practitioner_performance_report/practitioner_performance_report.js": {"from_date", "to_date", "branch", "practitioner"},
	"report/revenue_summary/revenue_summary.js": {"from_date", "to_date", "branch", "cost_center", "customer", "status", "service_category"},
	"report/unpaid_invoice_report/unpaid_invoice_report.js": {"from_date", "to_date", "branch", "customer", "age_range"},
	"report/dispensary_activity_report/dispensary_activity_report.js": {"from_date", "to_date", "branch", "warehouse", "item"},
	"report/stock_expiry_status/stock_expiry_status.js": {"company", "branch", "warehouse", "item_group", "expiry_buckets", "include_zero_qty"},
	"report/lab_order_report/lab_order_report.js": {"from_date", "to_date", "branch", "patient", "practitioner", "status"},
	"report/vaccination_report/vaccination_report.js": {"from_date", "to_date", "branch", "patient", "owner", "vaccine", "practitioner", "status", "due_status"},
	"report/boarding_report/boarding_report.js": {"from_date", "to_date", "branch", "patient", "owner", "kennel", "status"},
	"report/grooming_report/grooming_report.js": {"from_date", "to_date", "branch", "patient", "owner", "assigned_staff", "status"},
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

	def test_report_definitions_expose_expected_filters(self):
		for relative_path, expected_filters in EXPECTED_REPORT_FILTER_FIELDS.items():
			with self.subTest(target=relative_path):
				data = json.loads((VETERINARY_ROOT / relative_path).read_text())
				self.assertEqual({row["fieldname"] for row in data.get("filters", [])}, expected_filters)

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

	def test_workspace_rules_no_longer_use_alias_role_snippets(self):
		source = WORKSPACE_PATH.read_text()
		for alias in (
			"VetEdge Nurse",
			"VetEdge Branch Manager",
			"VetEdge Accounts/Cashier",
			"VetEdge Dispensary User",
			"VetEdge Lab Technician",
		):
			with self.subTest(alias=alias):
				self.assertNotIn(alias, source)

	def test_reports_apply_visibility_default_helper(self):
		for relative_path, report_name in REPORT_JS_WITH_DEFAULTS.items():
			with self.subTest(target=relative_path):
				source = (VETERINARY_ROOT / relative_path).read_text()
				self.assertIn("window.vetedgeReportVisibility?.apply", source)
				self.assertIn(report_name, source)

	def test_report_js_exposes_expected_filter_fields(self):
		for relative_path, expected_fieldnames in EXPECTED_REPORT_JS_FILTER_FIELDS.items():
			with self.subTest(target=relative_path):
				source = (VETERINARY_ROOT / relative_path).read_text()
				for fieldname in expected_fieldnames:
					self.assertIn(f'fieldname: "{fieldname}"', source)

	def test_shared_assets_include_report_visibility_helper(self):
		hooks_source = (VETERINARY_ROOT.parent / "hooks.py").read_text()
		self.assertIn("/assets/vetedge/js/report_visibility.js", hooks_source)
		dashboard_shell = (PUBLIC_ROOT / "dashboard_shell.js").read_text()
		self.assertIn("window.vetedgeReportVisibility.applyDashboard", dashboard_shell)
