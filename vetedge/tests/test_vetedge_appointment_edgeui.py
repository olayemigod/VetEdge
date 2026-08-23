from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "vetedge" / "services" / "appointment_edgeui.py"
BRIDGE = ROOT / "vetedge" / "services" / "appointment_grooming_bridge.py"
SMART_ACTIONS = ROOT / "vetedge" / "services" / "appointment_actions.py"
SMART_INTELLIGENCE = ROOT / "vetedge" / "services" / "appointment_intelligence.py"
PRACTITIONER_INTEGRITY = ROOT / "vetedge" / "services" / "practitioner_integrity.py"
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeAppointmentFlow.vue"
)
RESOURCE_COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeResourceCenter.vue"
)
BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_resource_center.bundle.js"
CLINICAL_EDITOR = ROOT / "vetedge" / "public" / "js" / "vetedge_clinical_record_editor.bundle.js"
FRONT_DESK_BUNDLE = ROOT / "vetedge" / "public" / "js" / "vetedge_front_desk_action_center.bundle.js"
SERVICE_COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_service_operations"
	/ "VetEdgeServiceOperations.vue"
)
APPOINTMENT_CONTROLLER = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_appointment"
	/ "veterinary_appointment.py"
)
APPOINTMENT_CLIENT = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_appointment"
	/ "veterinary_appointment.js"
)
APPOINTMENT_SCHEMA = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_appointment"
	/ "veterinary_appointment.json"
)
SESSION_CONTROLLER = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "pet_grooming_session"
	/ "pet_grooming_session.py"
)
SESSION_SCHEMA = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "pet_grooming_session"
	/ "pet_grooming_session.json"
)
CONSULTATION_CONTROLLER = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_consultation"
	/ "veterinary_consultation.py"
)
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


def test_appointment_links_are_permission_context_and_service_aware():
	content = read(API)

	for contract in (
		"search_appointment_link",
		"frappe.has_permission(doctype, \"read\")",
		"frappe.get_list(",
		"get_assigned_branches",
		"get_veterinary_doctor_users",
		"get_grooming_staff_users",
		"Branch Practitioner Assignment",
		'if field == "consultation_type"',
		'filters["disabled"] = ["!=", 1]',
		'def _search_vaccines(',
		'"species": species',
		'["is", "not set"]',
		'def _search_follow_up_consultations(',
		'{"patient": patient, "status": ["!=", "Cancelled"]}',
		'if field == "vaccine"',
		'if field == "follow_up_reference"',
		'if field == "groomer"',
		'if field == "grooming_service"',
	):
		assert contract in content

	assert "ignore_permissions=True" not in content
	assert "frappe.db.sql(" not in content


def test_new_appointment_creation_uses_one_scheduler_without_boarding_duplication():
	content = read(API)

	assert 'APPOINTMENT_TYPES = ("Consultation", "Follow Up", "Vaccination", "Grooming", "Other")' in content
	assert 'APPOINTMENT_TYPES = ("Consultation", "Follow Up", "Vaccination", "Grooming", "Boarding", "Other")' not in content
	for contract in (
		"create_edgeui_appointment",
		'frappe.has_permission("Veterinary Appointment", "create")',
		"can_access_branch_data",
		'PRACTITIONER_REQUIRED_TYPES = {"Consultation", "Follow Up", "Vaccination"}',
		'if appointment_type == "Follow Up":',
		"Originating Consultation is required for Follow Up appointments.",
		"Originating Consultation must belong to the selected patient.",
		'if appointment_type == "Vaccination":',
		"Planned Vaccine is required for Vaccination appointments.",
		'if appointment_type == "Grooming":',
		"Grooming Service and Groomer are required for Grooming appointments.",
		'if appointment_type == "Other" and not notes:',
		"Reason / Notes is required for Other appointments.",
		"Veterinary Practitioner is required for this appointment type.",
		"validate_doctor_user(practitioner)",
		'"consultation_type": consultation_type or None',
		'"follow_up_reference": follow_up_reference or None',
		'"vaccine": vaccine or None',
		'"grooming_service": grooming_service or None',
		'"groomer": groomer or None',
		'"status": "Scheduled"',
		'"created_from": "Manual"',
		'"primary_owner": patient_values.primary_owner',
	):
		assert contract in content

	assert "doc.submit(" not in content
	assert "Sales Invoice" not in content
	assert "Payment Entry" not in content


def test_appointment_flow_is_patient_first_and_switches_fields_by_service():
	content = read(COMPONENT)

	for contract in (
		"EdgeModal",
		"EdgeLinkField",
		"EdgeDropdown",
		'label="Veterinary Patient"',
		'label="Service Branch"',
		'label="Consultation Type"',
		'label="Originating Consultation"',
		'label="Planned Vaccine"',
		"requiresPractitioner ? 'Veterinary Practitioner' : 'Veterinary Practitioner (Optional)'",
		'label="Grooming Service"',
		'label="Groomer"',
		'v-if="hasConsultationContext"',
		'v-if="isFollowUp"',
		'v-if="isVaccination"',
		'v-if="!isGrooming"',
		'v-if="isGrooming"',
		"Populated from selected patient",
		"patientSpecies",
		"searchConsultationType",
		"searchFollowUpReference",
		"searchVaccine",
		"searchGroomingService",
		"searchGroomer",
		"create_edgeui_appointment",
	):
		assert contract in content

	assert '["Consultation", "Follow Up", "Vaccination", "Grooming", "Other"]' in content
	assert '"Boarding"' not in content
	assert "frappe.ui.Dialog" not in content
	assert "frappe.new_doc" not in content
	assert "window.open" not in content


def test_appointment_submit_sends_only_fields_relevant_to_selected_service():
	content = read(COMPONENT)

	for contract in (
		"patient: this.form.patient",
		"branch: this.form.branch",
		'practitioner: this.isGrooming ? "" : this.form.practitioner',
		"consultation_type: this.hasConsultationContext ? this.form.consultation_type",
		"follow_up_reference: this.isFollowUp ? this.form.follow_up_reference",
		"vaccine: this.isVaccination ? this.form.vaccine",
		"grooming_service: this.isGrooming ? this.form.grooming_service",
		"groomer: this.isGrooming ? this.form.groomer",
		"Consultation Type is required for Consultation and Follow Up appointments.",
		"Originating Consultation is required for Follow Up appointments.",
		"Planned Vaccine is required for Vaccination appointments.",
		"Grooming Service and Groomer are required for Grooming appointments.",
		"Veterinary Practitioner is required for this appointment type.",
		"Reason / Notes is required for Other appointments.",
	):
		assert contract in content

	assert "owner: this.form.owner" not in content


def test_smart_appointment_context_is_server_enforced_and_backward_compatible():
	intelligence = read(SMART_INTELLIGENCE)
	controller = read(APPOINTMENT_CONTROLLER)
	schema = read(APPOINTMENT_SCHEMA)
	consultation_controller = read(CONSULTATION_CONTROLLER)

	for contract in (
		'CONSULTATION_APPOINTMENT_TYPES = {"Consultation", "Follow Up"}',
		'PRACTITIONER_REQUIRED_APPOINTMENT_TYPES = {"Consultation", "Follow Up", "Vaccination"}',
		"prepare_appointment_service_context",
		"validate_appointment_service_context",
		"get_originating_consultation",
		"resolve_appointment_vaccine",
		"resolve_appointment_consultation_type",
		"_is_new_or_type_changed",
		"Originating Consultation is required for a new Follow Up appointment.",
		"Vaccine is required for a new Vaccination appointment.",
		"Reason / Notes is required for a new Other appointment.",
	):
		assert contract in intelligence

	assert "prepare_appointment_service_context(doc)" in controller
	assert "validate_appointment_service_context(doc)" in controller
	assert '"fieldname": "consultation_type"' in schema
	assert '"fieldname": "follow_up_reference"' in schema
	assert '"fieldname": "vaccine"' in schema
	assert '"label": "Reason / Notes"' in schema
	assert "appointment.get(\"consultation_type\")" in consultation_controller
	assert "appointment.follow_up_reference" in consultation_controller
	assert 'doc.consultation_type = "General Consultation"' in consultation_controller


def test_resource_center_uses_typed_appointment_deep_links_and_contextual_clinical_create():
	bundle = read(BUNDLE)
	resource_component = read(RESOURCE_COMPONENT)
	clinical_editor = read(CLINICAL_EDITOR)
	loader = read(LOADER)

	for contract in (
		"VetEdgeAppointmentFlow",
		"runtime.components?.EdgeLinkField",
		"flowApp.unmount()",
		"flowHost.remove()",
		"this.resource === 'appointments'",
		"appointment_type",
		"flowView?.open?.({ appointment_type: state.appointmentType || '' })",
		"LEGACY_GROOMING_RESOURCE = 'grooming'",
		"filter((option) => option.value !== LEGACY_GROOMING_RESOURCE)",
		"patient: this.clinicalFilters?.patient || ''",
		"service_branch: this.clinicalFilters?.service_branch || ''",
		"vaccine: this.resource === 'vaccinations'",
		"editor.create(this.clinicalDoctype, () => this.loadPage(), defaults)",
	):
		assert contract in bundle

	for contract in (
		"withCreateDefaults",
		"buildFieldSpecs(schema.fields || [], defaults)",
		"openCreateModal({ doctype, onSaved, defaults })",
		"create: (doctype, onSaved, defaults = {})",
	):
		assert contract in clinical_editor

	for contract in (
		'if (this.resource === "appointments") return "New Appointment";',
		'@action="runPrimaryAction"',
		"runPrimaryAction()",
	):
		assert contract in resource_component

	for retired in (
		"stopImmediatePropagation",
		"MutationObserver",
		"target.addEventListener('click', interceptAppointmentAction, true)",
	):
		assert retired not in bundle

	assert "EdgeLinkField" in loader
	assert "EdgeModal" in loader
	assert "EdgeDropdown" in loader
	assert "window.mountVetEdgeResourceCenter" in loader


def test_grooming_appointment_bridge_preserves_legacy_records_but_uses_veterinary_appointment_for_new_sessions():
	bridge = read(BRIDGE)
	appointment_controller = read(APPOINTMENT_CONTROLLER)
	appointment_client = read(APPOINTMENT_CLIENT)
	appointment_schema = read(APPOINTMENT_SCHEMA)
	session_controller = read(SESSION_CONTROLLER)
	session_schema = read(SESSION_SCHEMA)
	consultation_controller = read(CONSULTATION_CONTROLLER)
	practitioner_integrity = read(PRACTITIONER_INTEGRITY)

	for contract in (
		'GROOMING_APPOINTMENT_TYPE = "Grooming"',
		"validate_grooming_veterinary_appointment",
		"create_grooming_session_from_veterinary_appointment",
		'filters={"veterinary_appointment": appointment_doc.name}',
		'"veterinary_appointment": appointment_doc.name',
		"can_access_branch_data(get_current_user(), appointment_doc.branch, raise_exception=True)",
		"sync_veterinary_appointment_from_grooming_session",
	):
		assert contract in bridge

	assert 'doc.get("appointment_type") == "Grooming"' in appointment_controller
	assert "validate_grooming_veterinary_appointment(doc)" in appointment_controller
	assert "appointment_actions.get_appointment_action_state" in appointment_client
	assert "appointment_actions.perform_appointment_action" in appointment_client
	assert "Create / Open Grooming Session" not in appointment_client
	assert '"fieldname": "grooming_service"' in appointment_schema
	assert '"fieldname": "groomer"' in appointment_schema
	assert '"fieldname": "veterinary_appointment"' in session_schema
	assert "Legacy Grooming Appointment" in session_schema
	assert "validate_veterinary_appointment_grooming_session" in session_controller
	assert 'CONSULTATION_APPOINTMENT_TYPES = {"", "Consultation", "Follow Up"}' in consultation_controller
	assert "appointment_type not in CONSULTATION_APPOINTMENT_TYPES" in consultation_controller
	assert "validate_linked_appointment_service_type(self)" in consultation_controller
	assert 'doc.get("appointment_type") or ""' in practitioner_integrity
	assert '== "Grooming"' in practitioner_integrity


def test_smart_appointment_actions_are_type_and_status_aware_across_form_and_front_desk():
	actions = read(SMART_ACTIONS)
	appointment_client = read(APPOINTMENT_CLIENT)
	front_desk_bundle = read(FRONT_DESK_BUNDLE)

	for contract in (
		'CONSULTATION_APPOINTMENT_TYPES = {"Consultation", "Follow Up"}',
		'"start_consultation", label',
		'appointment_type == "Grooming"',
		'"start_grooming_session", "Create Grooming Session"',
		'appointment_type == "Vaccination"',
		'"vaccination_workflow", "Open Vaccination Workflow"',
		"resolve_appointment_vaccine(doc)",
		'params.append(f"vaccine={quote(cstr(vaccine))}")',
		'appointment_type == "Boarding"',
		'"boarding_operations", "Open Boarding Operations"',
		'appointment_type == "Other" and status == "Checked In"',
		"Only Consultation and Follow Up appointments can start a Veterinary Consultation.",
		"This action is no longer valid for the appointment type or status.",
	):
		assert contract in actions

	assert "Start Consultation" not in appointment_client
	assert "Create / Open Grooming Session" not in appointment_client
	assert "get_appointment_action_state" in appointment_client
	assert "perform_appointment_action" in appointment_client
	assert 'frm.set_query("consultation_type"' in appointment_client
	assert 'frm.set_query("follow_up_reference"' in appointment_client
	assert 'frm.set_query("vaccine"' in appointment_client
	assert "get_appointment_action_state" in front_desk_bundle
	assert "perform_appointment_action" in front_desk_bundle
	assert "loadSmartAppointmentState" in front_desk_bundle
	assert "originalOpenQueueDetail" in front_desk_bundle


def test_hospital_services_uses_business_documents_and_generic_veterinary_wording():
	content = read(SERVICE_COMPONENT)

	assert '{ value: "grooming-appointments"' not in content
	assert '{ value: "grooming-sessions", label: "Grooming Sessions"' in content
	assert 'if (["boarding-bookings", "boarding-stays"].includes(this.resource)) return "New Boarding Booking";' in content
	assert 'if (this.resource === "grooming-sessions") return "New Grooming Appointment";' in content
	assert "/desk/vetedge-resource-center?resource=appointments&new=1&appointment_type=Grooming" in content
	assert "<strong>Veterinary</strong>" in content
	assert "<strong>EdgeSuite</strong>" not in content
	assert 'active-route="/desk/vetedge-service-operations"' in content
	assert "`/desk/vetedge-service-operations?${params.toString()}`" in content
	assert 'action.key === "open-veterinary-appointment"' in content
	assert "/desk/pet-grooming-appointment/" in content
