from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "vetedge" / "services" / "appointment_edgeui.py"
PATIENT_CREATE_API = ROOT / "vetedge" / "services" / "appointment_patient_quick_create.py"
QUICK_CREATE_SAFETY = ROOT / "vetedge" / "services" / "appointment_quick_create_safety.py"
COMPANY_CONTEXT = ROOT / "vetedge" / "services" / "company_context.py"
HOOKS = ROOT / "vetedge" / "hooks.py"
PATIENT_CONTROLLER = (
	ROOT
	/ "vetedge"
	/ "veterinary"
	/ "doctype"
	/ "veterinary_patient"
	/ "veterinary_patient.py"
)
COMPONENT = (
	ROOT
	/ "vetedge"
	/ "public"
	/ "js"
	/ "vetedge_resource_center"
	/ "VetEdgeAppointmentFlowV2.vue"
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
BACKFILL_PATCH = ROOT / "vetedge" / "patches" / "backfill_veterinary_company_context.py"
SCHEMA_PATCH = ROOT / "vetedge" / "patches" / "repair_veterinary_company_schema.py"
AGE_PATCH = ROOT / "vetedge" / "patches" / "backfill_veterinary_patient_age_v1.py"
PATCHES = ROOT / "vetedge" / "patches.txt"


def read(path: Path) -> str:
	return path.read_text(encoding="utf-8")


def test_appointment_links_are_permission_company_and_context_aware():
	content = read(API)
	for contract in (
		"search_appointment_link",
		'frappe.has_permission(doctype, "read")',
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
		"this.bootstrap.active_company",
		"this.form.owner = context.primary_owner",
		"this.labels.owner = context.primary_owner_label",
		"this.clearPatient()",
	):
		assert contract in api or contract in bundle
	assert "option?.raw?.raw" not in bundle


def test_active_company_is_visible_and_locked_across_the_appointment_flow():
	component = read(COMPONENT)
	bundle = read(BUNDLE)
	for contract in (
		"Active Company: ${company}",
		"company: this.bootstrap.active_company",
		"this.patientDraft.company = this.bootstrap.active_company",
		"this.ownerDraft.company = this.bootstrap.active_company",
	):
		assert contract in bundle
	for contract in (
		'<span>Company</span>',
		':value="bootstrap.active_company"',
		'company: this.bootstrap.active_company',
	):
		assert contract in component


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


def test_complete_patient_create_keeps_vetedge_validation_and_system_billing_truth():
	content = read(PATIENT_CREATE_API)
	for contract in (
		"create_full_appointment_patient",
		'frappe.has_permission("Veterinary Patient", "create")',
		'frappe.db.has_column("Veterinary Patient", "company")',
		"validate_customer_company(owner, company)",
		"validate_patient_quick_create_context(company, branch)",
		"_find_patient_duplicate",
		"Breed must belong to the selected Species",
		'"company": company',
		'"neuter_status"',
		'"date_of_birth"',
		'"weight_baseline"',
		'"emergency_contact"',
		'"status": "Active"',
		'"is_deceased": 0',
		"doc.insert()",
	):
		assert contract in content
	assert "registration_invoice" not in content
	assert "registration_billed" not in content
	assert "registration_fee_amount" not in content
	assert "ignore_permissions" not in content


def test_quick_owner_creation_keeps_loyalty_outside_appointment_flow():
	api = read(API)
	safety = read(QUICK_CREATE_SAFETY)
	component = read(COMPONENT)
	for contract in (
		"resolve_owner_loyalty_program",
		"vetedge_skip_customer_loyalty_auto_enrollment",
		"disable_customer_loyalty_auto_enrollment_for_quick_create",
		"restore_customer_loyalty_auto_enrollment_after_quick_create",
		'doc.__dict__["set_loyalty_program"] = lambda: None',
		'doc.loyalty_program = None',
		'"default_currency": context.get("company_currency") or None',
		'"default_price_list": context.get("default_price_list") or None',
	):
		assert contract in api or contract in safety
	owner_context = safety.split("def get_owner_quick_create_context", 1)[1].split(
		"def resolve_owner_loyalty_program", 1
	)[0]
	assert '"loyalty_programs": []' in owner_context
	assert '"requires_loyalty_program": False' in owner_context
	assert "get_applicable_loyalty_programs(" not in owner_context
	assert "owner_loyalty_programs" not in component
	assert "Loyalty Program" not in component
	assert "ignore_permissions" not in safety


def test_registration_invoice_currency_is_scoped_to_patient_company_and_draft_only():
	safety = read(QUICK_CREATE_SAFETY)
	hooks = read(HOOKS)
	controller = read(PATIENT_CONTROLLER)
	for contract in (
		"registration_invoice_context",
		"vetedge_registration_invoice_context",
		"align_registration_invoice_company_currency",
		'int(doc.get("docstatus") or 0) != 0',
		"doc.company = company",
		"doc.currency = currency",
		"doc.conversion_rate = 1",
		"doc.price_list_currency = currency",
		"doc.plc_conversion_rate = 1",
		"get_compatible_selling_price_list",
	):
		assert contract in safety
	assert "appointment_quick_create_safety.align_registration_invoice_company_currency" in hooks
	assert "with registration_invoice_context(self):" in controller
	assert "Currency Exchange" not in safety
	assert "doc.submit(" not in safety


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


def test_patient_and_appointment_company_fields_have_no_invalid_dynamic_default():
	patient = read(PATIENT_DOCTYPE)
	appointment = read(APPOINTMENT_DOCTYPE)
	for content in (patient, appointment):
		assert '"fieldname":"company"' in content or '"fieldname": "company"' in content
		assert '"options":"Company"' in content or '"options": "Company"' in content
		assert '":Company"' not in content
	assert '"reqd": 1' in patient
	assert '"reqd":1' in appointment or '"reqd": 1' in appointment
	assert '"search_fields": "patient_name,primary_owner,company' in patient
	assert '"search_fields":"patient,primary_owner,company' in appointment or '"search_fields": "patient,primary_owner,company' in appointment


def test_company_schema_repair_is_new_idempotent_migration_step():
	backfill = read(BACKFILL_PATCH)
	repair = read(SCHEMA_PATCH)
	patches = read(PATCHES)
	for contract in (
		"_single_allowed_customer_company",
		"single_site_company = companies[0] if len(companies) == 1 else None",
		"WHERE IFNULL(company, '') = ''",
		'frappe.db.set_value("Veterinary Patient"',
		"INNER JOIN `tabVeterinary Patient`",
	):
		assert contract in backfill
	for contract in (
		'frappe.reload_doc("veterinary", "doctype", "veterinary_patient", force=True)',
		'frappe.reload_doc("veterinary", "doctype", "veterinary_appointment", force=True)',
		'frappe.db.has_column("Veterinary Patient", "company")',
		'frappe.db.has_column("Veterinary Appointment", "company")',
		"backfill()",
	):
		assert contract in repair
	assert "vetedge.patches.backfill_veterinary_company_context" in patches
	assert "vetedge.patches.repair_veterinary_company_schema" in patches


def test_existing_site_age_patch_is_idempotent_and_accounting_safe():
	patch = read(AGE_PATCH)
	patches = read(PATCHES)
	for contract in (
		"calculate_age_label",
		'frappe.db.set_value(',
		'"approximate_age"',
		"update_modified=False",
	):
		assert contract in patch
	assert "vetedge.patches.backfill_veterinary_patient_age_v1" in patches
	assert "Sales Invoice" not in patch
	assert "Payment Entry" not in patch


def test_patient_create_form_contains_all_operational_registration_fields():
	component = read(COMPONENT)
	for contract in (
		"Complete the clinical identity fields now",
		"Patient Name",
		"Pet Owner",
		"Default Branch",
		"Species",
		"Breed",
		"Sex",
		"Neuter Status",
		"Date of Birth",
		"Age",
		"patientAge",
		"calculateAgeLabel",
		"Date of Birth cannot be in the future",
		"Baseline Weight",
		"Colour / Markings",
		"Microchip ID",
		"Emergency Contact",
		"appointment_patient_quick_create.create_full_appointment_patient",
	):
		assert contract in component
	assert "registration invoice and billing fields remain system-managed" in component.lower()
	assert "frappe.ui.Dialog" not in component
	assert "frappe.new_doc" not in component
	assert "window.open" not in component


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
		"Back to Patient",
		"Existing patients can still be booked",
	):
		assert contract in component
	assert 'return this.searchLink("patient", query, { owner:' not in component
	assert ':disabled="!form.owner' not in component


def test_resource_center_mounts_new_complete_appointment_flow():
	bundle = read(BUNDLE)
	loader = read(LOADER)
	for contract in (
		"VetEdgeAppointmentFlowV2.vue",
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
	):
		assert contract in bundle
	assert "EdgeLinkField" in loader
	assert "EdgeModal" in loader
	assert "EdgeSuite UI 0.4.0 or newer" in loader
	assert "window.mountVetEdgeResourceCenter" in loader
