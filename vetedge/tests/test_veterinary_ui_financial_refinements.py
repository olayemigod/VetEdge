import json
from collections import Counter
from pathlib import Path

try:
	from frappe.tests.utils import FrappeTestCase
except ImportError:
	FrappeTestCase = None

ROOT = Path(__file__).resolve().parents[2]


def read(*parts: str) -> str:
	return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_diagnosis_types_use_approved_veterinary_order_and_safe_patch():
	data = json.loads(
		read(
			"vetedge",
			"veterinary",
			"doctype",
			"consultation_diagnosis",
			"consultation_diagnosis.json",
		)
	)
	field = next(row for row in data["fields"] if row.get("fieldname") == "diagnosis_type")
	assert field["options"].splitlines()[1:] == [
		"Differential",
		"Confirmed/Definitive",
		"Working",
		"Presumptive",
		"Ruled Out",
		"Others",
	]
	patch = read("vetedge", "patches", "normalize_consultation_diagnosis_types_v1.py")
	patches = read("vetedge", "patches.txt")
	assert '"Primary": "Working"' in patch
	assert '"Rule Out": "Ruled Out"' in patch
	assert '"Resolved": "Others"' in patch
	assert "normalize_consultation_diagnosis_types_v1" in patches
	for forbidden in ("Veterinary Consultation` SET", "DELETE FROM", "doc.submit"):
		assert forbidden not in patch


def test_settings_use_edgesuite_ui_while_preserving_native_single_doctype():
	client = read(
		"vetedge",
		"veterinary",
		"doctype",
		"veterinary_settings",
		"veterinary_settings.js",
	)
	component = read(
		"vetedge",
		"public",
		"js",
		"veterinary_settings_edgeui",
		"VeterinarySettingsHeader.vue",
	)
	bundle = read("vetedge", "public", "js", "veterinary_settings_edgeui.bundle.js")
	css = read("vetedge", "public", "css", "veterinary_settings_edgeui.css")
	assert 'frappe.ui.form.on("Veterinary Settings"' in client
	assert 'frappe.require("edgeui.bundle.js"' in client
	assert "mountVeterinarySettingsHeader" in client
	assert "EdgePageHeader" in component
	assert "EdgeStatusBadge" in component
	assert "runtime.createEdgeApp(root, props)" in bundle
	assert ".veterinary-settings-edgeui-form .form-section.card-section" in css
	assert '__("Enable Veterinary")' in client
	assert '__("Enable VetEdge")' not in client


def test_home_menu_descriptions_and_branding_identity_are_veterinary_facing():
	bridge = read("vetedge", "public", "js", "vetedge_ui_bridge.js")
	menu = read("vetedge", "public", "js", "edgesuite_product_menu.js")
	identity = read("vetedge", "ui_identity.py")
	assert '"/app/vetedge-home"' in bridge.split("const PRODUCT_ROUTES", 1)[1].split(");", 1)[0]
	assert "if (PRODUCT_ROUTES.has(path)) return openSameTab(route);" in bridge
	assert "MENU_DESCRIPTIONS" in menu
	assert "description: menuDescription(item)" in menu
	assert "html(menuDescription(item))" in menu
	assert 'html(item.link_type || "Workspace")' not in menu
	assert "portal_logo" in identity
	assert 'settings_brand.get("logo")' in identity
	assert 'tenant_logo = settings_brand.get("logo")' in identity
	assert '"product_name": "Veterinary"' in identity


def test_financial_dashboard_has_one_component_aware_income_view():
	page = read(
		"vetedge",
		"veterinary",
		"page",
		"veterinary_financial_dashboard",
		"veterinary_financial_dashboard.js",
	)
	dataset = read("vetedge", "services", "financial_dataset.py")
	insights = read("vetedge", "services", "financial_component_insights.py")
	logic = read("vetedge", "services", "reporting_logic_v5.py")
	hooks = read("vetedge", "hooks.py")
	assert '.find(".vetedge-dashboard-composition-section").remove()' in page
	assert '"Consultation Fee": "Consultation Service Income"' in dataset
	assert '"Treatment": "Treatment Income"' in dataset
	assert '"revenue_components"' in dataset
	assert '"consultation_service_income"' in dataset
	assert '"treatment_income"' in dataset
	assert '"Consultation Service Income"' in insights
	assert '"Treatment Income"' in insights
	assert '_("Revenue by Income Source")' in logic
	assert "@frappe.whitelist()" in logic
	assert '"vetedge.services.reporting_logic_v5.get_dashboard_payload"' in hooks
	assert "has_veterinary_vaccination_record_permission" in hooks
	assert "has_veterinary_vaccination_permission" not in hooks
	for forbidden in ("frappe.db.set_value", ".submit(", ".save(", "db_set("):
		assert forbidden not in dataset


def test_revenue_summary_exposes_consultation_and_treatment_income():
	report = read("vetedge", "services", "financial_component_report.py")
	report_python = read(
		"vetedge",
		"veterinary",
		"report",
		"revenue_summary",
		"revenue_summary.py",
	)
	report_client = read(
		"vetedge",
		"veterinary",
		"report",
		"revenue_summary",
		"revenue_summary.js",
	)
	for fieldname in (
		"consultation_service_income",
		"treatment_income",
		"laboratory_income",
		"vaccination_income",
		"other_income",
	):
		assert fieldname in report
	assert "execute_revenue_summary" in report_python
	assert 'fieldname: "income_category"' in report_client
	assert '"Consultation Service Income"' in report_client
	assert '"Treatment Income"' in report_client
	assert "docstatus" in report
	for forbidden in ("frappe.db.set_value", ".submit(", ".save(", "db_set("):
		assert forbidden not in report


if FrappeTestCase is not None:
	class TestVeterinaryRevenueAllocation(FrappeTestCase):
		def test_invoice_total_reconciles_across_service_and_treatment_components(self):
			from vetedge.services.financial_dataset import _allocate_revenue_components

			source_map = {
				"INV-TEST": {
					"CONSULT": Counter({"Consultation Service Income": 1}),
					"TREAT": Counter({"Treatment Income": 1}),
				}
			}
			item_map = {
				"INV-TEST": [
					{"item_code": "CONSULT", "net_amount": 20},
					{"item_code": "TREAT", "net_amount": 80},
				]
			}
			components = _allocate_revenue_components(
				"INV-TEST",
				"Consultation",
				110,
				60,
				50,
				source_map,
				item_map,
			)
			by_category = {row["category"]: row for row in components}
			self.assertAlmostEqual(by_category["Consultation Service Income"]["amount"], 22)
			self.assertAlmostEqual(by_category["Treatment Income"]["amount"], 88)
			self.assertAlmostEqual(sum(row["amount"] for row in components), 110)
			self.assertAlmostEqual(sum(row["paid_amount"] for row in components), 60)
			self.assertAlmostEqual(sum(row["outstanding_amount"] for row in components), 50)
