from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "vetedge" / "services" / "pricing_master_workspace.py"
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_pricing_master_workspace"
	/ "VetEdgePricingMasterWorkspace.vue"
)
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_pricing_master_workspace.bundle.js"
PAGE_ROOT = ROOT / "vetedge" / "veterinary" / "page" / "vetedge_pricing_master_workspace"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_phase_2b_scope_is_explicit_and_operational_documents_are_excluded():
	content = read(SERVICE)
	for resource, doctype in (
		("treatment-items", "Veterinary Treatment Item"),
		("treatment-types", "Veterinary Treatment Type"),
		("lab-tests", "Veterinary Lab Test"),
		("vaccines", "Veterinary Vaccine"),
		("grooming-services", "Pet Grooming Service"),
	):
		assert f'"{resource}":' in content
		assert f'"doctype": "{doctype}"' in content

	for excluded in (
		"Veterinary Consultation",
		"Veterinary Lab Order",
		"Veterinary Vaccination Record",
		"Pet Grooming Appointment",
		"Pet Grooming Session",
		"Sales Invoice",
		"Payment Entry",
		"Stock Entry",
	):
		assert f'"doctype": "{excluded}"' not in content


def test_pricing_service_preserves_permissions_controllers_and_accounting_safety():
	content = read(SERVICE)
	for contract in (
		"require_internal_user()",
		"frappe.has_permission",
		'doc.check_permission("read")',
		'doc.check_permission("write")',
		'doc.check_permission("delete")',
		"require_vetedge_platform_access",
		"frappe.TimestampMismatchError",
		"doc.insert()",
		"doc.save()",
		"frappe.delete_doc",
		"frappe.get_list",
	):
		assert contract in content

	for forbidden in (
		"ignore_permissions=True",
		"frappe.db.set_value",
		"doc.submit()",
		"doc.cancel()",
		'frappe.get_doc("Sales Invoice"',
		'frappe.get_doc("Payment Entry"',
		'frappe.get_doc("Stock Entry"',
	):
		assert forbidden not in content


def test_pricing_links_are_filtered_and_validated_on_the_server():
	content = read(SERVICE)
	for contract in (
		'"item": {"disabled": 0, "is_sales_item": 1}',
		'"linked_item": {"disabled": 0, "is_sales_item": 1, "is_stock_item": 0}',
		'"default_item": {"disabled": 0, "is_sales_item": 1, "is_stock_item": 0}',
		'"price_list": {"enabled": 1, "selling": 1}',
		'_assert_active_link("Veterinary Species"',
		'_assert_active_link("Veterinary Service Type"',
		'_assert_active_link("Veterinary Treatment Type"',
		"must be an enabled ERPNext sales Item",
		"must be a non-stock ERPNext Item",
		"must be a selling Price List",
	):
		assert contract in content


def test_pricing_forms_preserve_sections_and_lock_identity_after_insert():
	content = read(SERVICE)
	for contract in (
		"_build_form_schema",
		'field.fieldtype == "Tab Break"',
		'field.fieldtype == "Section Break"',
		'field.fieldtype == "Column Break"',
		"identity_fields",
		"not is_new and field.fieldname in identity_fields",
		"is_new or field.fieldname not in identity_fields",
		'"side_effects": ["item_price", "item_shelf_life"]',
		"updates the linked ERPNext Item Price",
	):
		assert contract in content


def test_pricing_page_is_full_edgesuite_and_uses_collision_safe_runtime():
	for path in (
		SERVICE,
		COMPONENT,
		BUNDLE,
		PAGE_ROOT / "vetedge_pricing_master_workspace.js",
		PAGE_ROOT / "vetedge_pricing_master_workspace.json",
	):
		assert path.exists(), path

	component = read(COMPONENT)
	loader = read(PAGE_ROOT / "vetedge_pricing_master_workspace.js")
	bundle = read(BUNDLE)
	for contract in (
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeFilterBar",
		"EdgeDataTable",
		"EdgeDocumentForm",
		"EdgeWorkflowBar",
		"EdgeLinkField",
		"EdgeModal",
		"EdgeLoadingState",
		"EdgeEmptyState",
		"EdgeErrorState",
		"Before you save",
		"Save behaviour",
	):
		assert contract in component

	for resource in (
		"treatment-items",
		"treatment-types",
		"lab-tests",
		"vaccines",
		"grooming-services",
	):
		assert resource in component

	assert "frappe.ui.form" not in component
	assert "cur_frm" not in component
	assert "frappe.require('edgesuite_ui.bundle.js'" in loader
	assert "const runtime = window.EdgeSuiteUI;" in loader
	assert "frappe.require('edgeui.bundle.js'" not in loader
	assert "applyWorkspaceSafety(VetEdgePricingMasterWorkspace)" in bundle


def test_native_phase_2b_routes_redirect_to_the_pricing_workspace():
	for folder, file_stem, doctype, resource in (
		("veterinary_treatment_item", "veterinary_treatment_item", "Veterinary Treatment Item", "treatment-items"),
		("veterinary_treatment_type", "veterinary_treatment_type", "Veterinary Treatment Type", "treatment-types"),
		("veterinary_lab_test", "veterinary_lab_test", "Veterinary Lab Test", "lab-tests"),
		("veterinary_vaccine", "veterinary_vaccine", "Veterinary Vaccine", "vaccines"),
		("pet_grooming_service", "pet_grooming_service", "Pet Grooming Service", "grooming-services"),
	):
		root = ROOT / "vetedge" / "veterinary" / "doctype" / folder
		form = read(root / f"{file_stem}.js")
		listview = read(root / f"{file_stem}_list.js")
		assert f"frappe.ui.form.on('{doctype}'" in form
		assert f"frappe.listview_settings['{doctype}']" in listview
		assert f"resource={resource}" in form
		assert f"resource={resource}" in listview
		assert "/app/vetedge-pricing-master-workspace" in form
		assert "/app/vetedge-pricing-master-workspace" in listview
