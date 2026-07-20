from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "vetedge" / "services" / "appointment_edgeui.py"
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeAppointmentFlow.vue"
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

	assert 'frappe.get_doc({"doctype": "DocType"' not in content
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


def test_appointment_flow_is_patient_first_and_derives_owner_from_patient():
	content = read(COMPONENT)

	patient_field = content.index('label="Veterinary Patient"')
	owner_summary = content.index("vetedge-appointment-flow-owner-summary")
	assert patient_field < owner_summary

	for contract in (
		"Search the patient first",
		"optionRecord(option)",
		"option?.raw?.raw || option?.raw",
		"record.primary_owner",
		"Automatically filled from the selected patient",
		'return this.searchLink("patient", query, { branch: this.form.branch })',
		"this.form.owner = record.primary_owner",
		"this.clearPatient()",
		"this.clearPractitioner()",
	):
		assert contract in content

	assert 'return this.searchLink("patient", query, { owner:' not in content
	assert ':disabled="!form.owner' not in content


def test_new_patient_can_search_or_create_owner_without_leaving_edgesuite():
	content = read(COMPONENT)

	for contract in (
		"EdgeModal",
		"EdgeLinkField",
		"Create New Veterinary Patient",
		"Create New Pet Owner",
		"createPatientFromQuery",
		"createOwnerForPatientFromQuery",
		"patientCreateResolve",
		"ownerCreateResolve",
		'v-show="screen === \'patient\'"',
		'v-show="screen === \'owner\'"',
		"onPatientOwnerSelected",
		"primary_owner: this.patientDraft.primary_owner",
		"Back to Patient",
		"create_appointment_owner",
		"create_appointment_patient",
		"create_edgeui_appointment",
		"searchSpecies",
		"searchBreed",
	):
		assert contract in content

	assert "frappe.ui.Dialog" not in content
	assert "frappe.new_doc" not in content
	assert "window.open" not in content


def test_resource_center_exposes_new_appointment_action_and_blocks_generic_editor():
	bundle = read(BUNDLE)
	loader = read(LOADER)

	for contract in (
		"VetEdgeAppointmentFlow",
		"runtime.components?.EdgeLinkField",
		"flowApp.unmount()",
		"flowHost.remove()",
		"this.resource === 'appointments'",
		"flowView?.open?.()",
		"New Appointment",
		"interceptAppointmentAction",
		"stopImmediatePropagation",
		"MutationObserver",
		"target.addEventListener('click', interceptAppointmentAction, true)",
	):
		assert contract in bundle

	assert "EdgeLinkField" in loader
	assert "EdgeModal" in loader
	assert "EdgeSuite UI 0.4.0 or newer" in loader
	assert "window.mountVetEdgeResourceCenter" in loader
