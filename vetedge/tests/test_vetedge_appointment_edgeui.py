from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "vetedge" / "services" / "appointment_edgeui.py"
COMPANY_CONTEXT = ROOT / "vetedge" / "services" / "company_context.py"
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
PATIENT_DOCTYPE = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_patient"
	/ "veterinary_patient.json"
)
APPOINTMENT_DOCTYPE = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_appointment"
	/ "veterinary_appointment.json"
)
PATCH = ROOT / "vetedge" / "patches" / "backfill_veterinary_company_context.py"
PATCHES = ROOT / "vetedge" / "patches.txt"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_appointment_links_are_permission_company_and_context_aware():
	content = read(API)

	for contract in (
		"search_appointment_link",
		"frappe.has_permission(doctype, \"read\")",
		"frappe.get_list(",
		'filters["primary_owner"] = context["owner"]',
		'filters["default_branch"]',
		'filters["company"] = company',
		"customer_is_allowed_for_company",
		"get_assigned_branches",
		"get_veterinary_doctor_users",
		"Branch Practitioner Assignment",
		'filters["species"] = context["species"]',
	):
		assert contract in content

	assert "ignore_permissions=True" not in content
	assert "frappe.db.sql(" not in content


def test_selected_patient_owner_is_resolved_server_side_for_active_company():
	api = read(API)
	bundle = read(BUNDLE)

	for contract in (
		"get_patient_selection_context",
		'filters={"name": _clean(patient), "company": company',
		"validate_customer_company(owner, company)",
		'"primary_owner_label": _owner_label(owner)',
		"get_patient_selection_context'",
		"this.bootstrap.active_company",
		"this.form.owner = context.primary_owner",
		"this.labels.owner = context.primary_owner_label",
		"this.clearPatient()",
	):
		assert contract in api or contract in bundle

	assert "option?.raw?.raw" not in bundle


def test_active_company_is_visible_and_locked_across_the_appointment_flow():
	bundle = read(BUNDLE)

	for contract in (
		"Active Company: ${company}",
		"company: this.bootstrap.active_company",
		"this.patientDraft.company = this.bootstrap.active_company",
		"this.ownerDraft.company = this.bootstrap.active_company",
		"originalAppointmentPayload",
		"originalCreatePatientFromQuery",
		"originalCreateOwnerForPatientFromQuery",
	):
		assert contract in bundle


def test_company_context_filters_restricted_customers_and_assigns_new_owners():
	content = read(COMPANY_CONTEXT)
	api = read(API)

	for contract in (
		"get_active_vetedge_company",
		"get_allowed_vetedge_companies",
		"validate_vetedge_company",
		"customer_is_allowed_for_company",
		'values.get("restrict_to_companies")',
		'"Company Restriction"',
		'"parentfield": "allowed_companies"',
		"apply_customer_company_restriction",
		'doc.restrict_to_companies = 1',
		'doc.append("allowed_companies", {"company": company})',
	):
		assert contract in content

	assert "apply_customer_company_restriction(doc, company)" in api
	assert "validate_customer_company(owner, company)" in api


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
		'"company": company',
		'"status": "Active"',
		"doc.insert()",
	):
		assert contract in content

	assert 'frappe.get_doc({"doctype": "DocType"' not in content
	assert "ignore_permissions" not in content


def test_appointment_creation_reuses_existing_validation_and_company_truth():
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
		'"company": company',
		"patient_values.company != company",
		"validate_customer_company(patient_values.primary_owner, company)",
	):
		assert contract in content

	assert "doc.submit(" not in content
	assert "Sales Invoice" not in content
	assert "Payment Entry" not in content


def test_patient_and_appointment_doctypes_persist_company_context():
	patient = read(PATIENT_DOCTYPE)
	appointment = read(APPOINTMENT_DOCTYPE)

	for content in (patient, appointment):
		assert '"fieldname": "company"' in content
		assert '"options": "Company"' in content
		assert '"default": ":Company"' in content

	assert '"search_fields": "patient_name,primary_owner,company' in patient
	assert '"search_fields": "patient,primary_owner,company' in appointment


def test_company_backfill_is_idempotent_and_safe_for_multi_company_sites():
	patch = read(PATCH)
	patches = read(PATCHES)

	for contract in (
		"_single_allowed_customer_company",
		"single_site_company = companies[0] if len(companies) == 1 else None",
		"WHERE IFNULL(company, '') = ''",
		'frappe.db.set_value("Veterinary Patient"',
		"INNER JOIN `tabVeterinary Patient`",
		"WHERE (a.company IS NULL OR a.company = '')",
	):
		assert contract in patch

	assert "vetedge.patches.backfill_veterinary_company_context" in patches


def test_appointment_flow_is_patient_first_and_owner_creation_stays_inside_edgesuite():
	component = read(COMPONENT)

	patient_field = component.index('label="Veterinary Patient"')
	owner_summary = component.index("vetedge-appointment-flow-owner-summary")
	assert patient_field < owner_summary

	for contract in (
		"Search the patient first",
		"Automatically filled from the selected patient",
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
		assert contract in component

	assert 'return this.searchLink("patient", query, { owner:' not in component
	assert ':disabled="!form.owner' not in component
	assert "frappe.ui.Dialog" not in component
	assert "frappe.new_doc" not in component
	assert "window.open" not in component


def test_resource_center_exposes_new_appointment_action_and_blocks_generic_editor():
	bundle = read(BUNDLE)
	loader = read(LOADER)

	for contract in (
		"VetEdgeAppointmentFlow",
		"AppointmentFlowRoot",
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
