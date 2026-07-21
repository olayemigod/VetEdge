import json
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


def test_operational_settings_page_is_full_edgesuite_ui_over_native_single_storage():
	loader = read(
		"vetedge",
		"veterinary",
		"page",
		"veterinary_settings_center",
		"veterinary_settings_center.js",
	)
	page_config = json.loads(
		read(
			"vetedge",
			"veterinary",
			"page",
			"veterinary_settings_center",
			"veterinary_settings_center.json",
		)
	)
	component = read(
		"vetedge",
		"public",
		"js",
		"veterinary_settings_center",
		"VeterinarySettingsCenter.vue",
	)
	bundle = read("vetedge", "public", "js", "veterinary_settings_center.bundle.js")
	api = read("vetedge", "services", "settings_page.py")

	assert page_config["name"] == "veterinary-settings-center"
	assert page_config["module"] == "Veterinary"
	assert 'frappe.require("edgeui.bundle.js"' in loader
	assert "veterinary_settings_center.bundle.js" in loader
	for edge_component in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeStatusBadge",
		"EdgeLinkField",
		"EdgeLoadingState",
		"EdgeErrorState",
	):
		assert edge_component in component
	assert "runtime.createEdgeApp(VeterinarySettingsCenter)" in bundle
	assert "get_veterinary_settings_page" in api
	assert "save_veterinary_settings_page" in api
	assert "search_veterinary_settings_link" in api
	assert 'SETTINGS_DOCTYPE = "Veterinary Settings"' in api
	assert "doc.save()" in api
	assert "ignore_permissions" not in api


def test_home_is_primary_menu_item_and_technical_keywords_are_replaced():
	config = read("vetedge", "public", "js", "vetedge_product_menu_config.js")
	hooks = read("vetedge", "hooks.py")
	bridge = read("vetedge", "public", "js", "vetedge_ui_bridge.js")

	assert "primary_item: primaryItem" in config
	assert 'item.label === "Veterinary Home"' in config
	assert 'item.link_to === "vetedge-home"' in config
	assert "primaryItem = primaryItem || item" in config
	assert "TECHNICAL_DESCRIPTIONS" in config
	for technical in ("page", "doctype", "report", "workspace", "link"):
		assert f'"{technical}"' in config
	assert "DESCRIPTIONS" in config
	assert 'normalized.link_to = "veterinary-settings-center"' in config
	assert 'normalized.route = "/app/veterinary-settings-center"' in config
	assert hooks.index("vetedge_product_menu_config.js") < hooks.index("edgesuite_product_menu.js")
	assert '"/app/veterinary-settings-center"' in bridge.split("const PRODUCT_ROUTES", 1)[1].split(");", 1)[0]
	assert "if (PRODUCT_ROUTES.has(path)) return openSameTab(route);" in bridge


def test_branding_identity_remains_veterinary_facing():
	identity = read("vetedge", "ui_identity.py")
	assert "portal_logo" in identity
	assert 'settings_brand.get("logo")' in identity
	assert 'tenant_logo = settings_brand.get("logo")' in identity
	assert '"product_name": "Veterinary"' in identity


def test_financial_dashboard_retains_cards_and_removes_only_duplicate_donut():
	page = read(
		"vetedge",
		"veterinary",
		"page",
		"veterinary_financial_dashboard",
		"veterinary_financial_dashboard.js",
	)
	shell = read("vetedge", "public", "js", "dashboard_shell.js")
	assert '.find(".vetedge-revenue-composition-chart-layout").remove()' in page
	assert ".vetedge-dashboard-composition-section" not in page.split(".remove()", 1)[0]
	assert "MutationObserver" in page
	assert "vetedge-revenue-composition-cards" in shell
	assert "vetedge-revenue-composition-chart-layout" in shell


def test_financial_dataset_uses_consultation_item_and_complete_service_mix():
	dataset = read("vetedge", "services", "financial_reporting_dataset.py")
	insights = read("vetedge", "services", "financial_component_insights.py")
	logic = read("vetedge", "services", "reporting_logic_v5.py")
	hooks = read("vetedge", "hooks.py")

	assert '_configured_consultation_item()' in dataset
	assert "item_code == consultation_item" in dataset
	assert "basis[CONSULTATION_SERVICE_INCOME]" in dataset
	assert "basis[TREATMENT_INCOME]" in dataset
	for category in (
		"Laboratory Income",
		"Vaccination Income",
		"Grooming Income",
		"Boarding Income",
		"Hospitalisation Income",
		"Dispensary Income",
		"Registration Income",
	):
		assert category in dataset
	assert "allocate_component_totals" in dataset
	assert "build_financial_dataset as build_legacy_financial_dataset" in dataset
	assert "from vetedge.services.financial_reporting_dataset import build_financial_dataset" in insights
	assert '_("Revenue by Income Source")' in logic
	assert "@frappe.whitelist()" in logic
	assert '"vetedge.services.reporting_logic_v5.get_dashboard_payload"' in hooks
	assert "has_veterinary_vaccination_record_permission" in hooks
	assert "has_veterinary_vaccination_permission" not in hooks
	for forbidden in ("frappe.db.set_value", ".submit(", ".save(", "db_set("):
		assert forbidden not in dataset


def test_revenue_summary_exposes_all_operational_income_sources():
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
		"grooming_income",
		"boarding_income",
		"hospitalisation_income",
		"dispensary_income",
		"registration_income",
		"other_income",
	):
		assert fieldname in report
	assert "execute_revenue_summary" in report_python
	assert 'fieldname: "income_category"' in report_client
	for category in (
		"Consultation Service Income",
		"Treatment Income",
		"Laboratory Income",
		"Vaccination Income",
		"Grooming Income",
		"Boarding Income",
		"Hospitalisation Income",
	):
		assert f'"{category}"' in report_client
	assert "docstatus" in report
	for forbidden in ("frappe.db.set_value", ".submit(", ".save(", "db_set("):
		assert forbidden not in report


if FrappeTestCase is not None:
	class TestVeterinaryRevenueAllocation(FrappeTestCase):
		def test_configured_consultation_item_and_treatment_lines_reconcile(self):
			from vetedge.services.financial_reporting_dataset import classify_financial_row

			row = {
				"sales_invoice": "INV-TEST",
				"consultation_reference": "VCONS-TEST",
				"grand_total": 110,
				"paid_amount": 60,
				"outstanding_amount": 50,
			}
			items = [
				{"item_code": "CONSULT", "net_amount": 20},
				{"item_code": "TREAT", "net_amount": 80},
			]
			classified = classify_financial_row(row, items, {}, "CONSULT")
			components = classified["revenue_components"]
			by_category = {component["category"]: component for component in components}

			self.assertAlmostEqual(classified["consultation_service_income"], 22)
			self.assertAlmostEqual(classified["treatment_income"], 88)
			self.assertAlmostEqual(by_category["Consultation Service Income"]["amount"], 22)
			self.assertAlmostEqual(by_category["Treatment Income"]["amount"], 88)
			self.assertAlmostEqual(sum(component["amount"] for component in components), 110)
			self.assertAlmostEqual(sum(component["paid_amount"] for component in components), 60)
			self.assertAlmostEqual(sum(component["outstanding_amount"] for component in components), 50)

		def test_linked_services_retain_their_own_income_categories(self):
			from vetedge.services.financial_reporting_dataset import classify_financial_row

			service_references = {
				"lab_reference": "Laboratory Income",
				"vaccination_reference": "Vaccination Income",
				"grooming_reference": "Grooming Income",
				"boarding_reference": "Boarding Income",
				"hospitalisation_reference": "Hospitalisation Income",
			}
			for reference_field, expected_category in service_references.items():
				with self.subTest(reference_field=reference_field):
					row = {
						"sales_invoice": f"INV-{reference_field}",
						reference_field: "REFERENCE",
						"grand_total": 25,
						"paid_amount": 25,
						"outstanding_amount": 0,
					}
					classified = classify_financial_row(
						row,
						[{"item_code": "SERVICE", "net_amount": 25}],
						{},
						"CONSULT",
					)
					self.assertEqual(classified["revenue_component_labels"], [expected_category])
