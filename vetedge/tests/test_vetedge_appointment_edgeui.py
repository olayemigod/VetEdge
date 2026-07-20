from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "vetedge" / "services" / "appointment_edgeui.py"
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeAppointmentQuickCreate.vue"
)
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_resource_center.bundle.js"
LOADER = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "page"
	/ "vetedge_resource_center"
	/ "vetedge_resource_center.js"
)


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_appointment_links_are_permission_and_context_aware():
	content = read(API)

	for contract in (
		"search_appointment_link",
		"frappe.has_permission(doctype, \"read\")",
		"frappe.get_list(",
		'filters["primary_owner"] = context["owner"]',
		'filters["default_branch"]',
		"get_assigned_branches",
		"get_veterinary_doctor_users",
		"Branch Practitioner Assignment",
		'filters["species"] = context["species"]',
	):
		assert contract in content

	assert "ignore_permissions=True" not in content
	assert "frappe.db.sql(" not in content


def test_create_new_owner_and_patient_keep_erpnext_and_vetedge_truth():
	content = read(API)

	for contract in (
		"create_appointment_owner",
		'frappe.has_permission("Customer", "create")',
		"get_default_customer_group",
		"get_default_territory",
		'"customer_type": "Individual"',
		"_find_owner_duplicate",
		"create_appointment_patient",
		'frappe.has_permission("Veterinary Patient", "create")',
		"_find_patient_duplicate",
		"Breed must belong to the selected Species",
		'"status": "Active"',
		"doc.insert()",
	):
		assert contract in content

	assert "frappe.get_doc({\"doctype\": \"DocType\"" not in content
	assert "ignore_permissions" not in content


def test_appointment_creation_reuses_existing_validation_and_permissions():
	content = read(API)

	for contract in (
		"create_edgeui_appointment",
		'frappe.has_permission("Veterinary Appointment", "create")',
		"can_access_branch_data",
		"validate_doctor_user",
		"get_datetime(appointment_datetime)",
		'"status": "Scheduled"',
		'"created_from": "Manual"',
		'"primary_owner": patient_values.primary_owner',
	):
		assert contract in content

	assert "doc.submit(" not in content
	assert "Sales Invoice" not in content
	assert "Payment Entry" not in content


def test_quick_create_uses_shared_link_field_and_cascading_clear_rules():
	content = read(COMPONENT)

	for contract in (
		"EdgeLinkField",
		"createOwnerFromQuery",
		"createPatientFromQuery",
		"searchOwner",
		"searchPatient",
		"searchBranch",
		"searchPractitioner",
		"this.clearPatient()",
		"this.clearPractitioner()",
		"create_appointment_owner",
		"create_appointment_patient",
		"create_edgeui_appointment",
		"Veterinary Breed",
		"filters: { species:",
	):
		assert contract in content


def test_resource_center_mounts_and_cleans_up_quick_create_consumer():
	bundle = read(BUNDLE)
	loader = read(LOADER)

	for contract in (
		"VetEdgeAppointmentQuickCreate",
		"runtime.components?.EdgeLinkField",
		"quickApp.unmount()",
		"quickHost.remove()",
		"this.resource === 'appointments'",
		"quickView?.open?.()",
	):
		assert contract in bundle

	assert "EdgeLinkField" in loader
	assert "EdgeModal" in loader
	assert "EdgeSuite UI 0.4.0 or newer" in loader
	assert "window.mountVetEdgeResourceCenter" in loader
