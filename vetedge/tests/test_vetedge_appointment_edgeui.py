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
		"get_assigned_branches",
		"get_veterinary_doctor_users",
		"Branch Practitioner Assignment",
		'filters["species"] = context["species"]',
	):
		assert contract in content

	assert "ignore_permissions=True" not in content
	assert "frappe.db.sql(" not in content


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

	for contract in (
		"EdgeModal",
		"EdgeLinkField",
		'label="Veterinary Patient"',
		'label="Service Branch"',
		"Populated from selected patient",
		"this.searchLink(\"patient\", query)",
		"const raw = option?.raw || {}",
		"this.form.owner = raw.primary_owner",
		"this.clearPractitioner()",
		"create_edgeui_appointment",
	):
		assert contract in content

	patient_position = content.index('label="Veterinary Patient"')
	owner_position = content.index("<span>Pet Owner</span>")
	branch_position = content.index('label="Service Branch"')
	assert patient_position < owner_position < branch_position

	assert ':disabled="!form.owner || !form.branch"' not in content
	assert 'placeholder="Search the selected owner\'s patients"' not in content
	assert "if (changed) this.clearPatient()" not in content
	assert "this.clearPatient();\n\t\t},\n\t\tclearBranch" not in content
	assert "frappe.ui.Dialog" not in content
	assert "frappe.new_doc" not in content
	assert "window.open" not in content


def test_appointment_submit_uses_patient_service_branch_and_practitioner():
	content = read(COMPONENT)

	for contract in (
		"patient: this.form.patient",
		"branch: this.form.branch",
		"practitioner: this.form.practitioner",
		"Patient, Service Branch, Practitioner and Appointment Date/Time are required.",
	):
		assert contract in content

	assert "owner: this.form.owner" not in content
	assert "Owner, Patient, Branch, Practitioner" not in content


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
	assert "window.mountVetEdgeResourceCenter" in loader
