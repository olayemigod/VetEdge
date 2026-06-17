from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime

from vetedge.services.appointment_flow import emit_appointment_event
from vetedge.services.billing import (
	PAID_STATUS,
	build_invoice_item,
	create_consultation_invoice,
	get_consultation_billing_settings,
	get_invoice_payment_status,
	validate_sales_item,
)
from vetedge.services.expiry_control import allocate_item_batches, summarize_allocations, validate_stock_item_expiry_configuration
from vetedge.services.feature_flags import is_enabled
from vetedge.services.notifications import emit_notification_event
from vetedge.services.permissions import (
	ELEVATED_ROLES,
	DOCTOR_ROLES,
	FRONT_DESK_ROLES,
	ROLE_VETERINARY_NURSE,
	can_access_branch_data,
	can_access_consultation,
	get_assigned_branches,
	get_current_user,
	is_internal_staff_user,
	user_has_any_role,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import get_billing_cost_center, get_default_company
from vetedge.services.stock import (
	build_stock_entry_rows,
	get_branch_dispensary_warehouse,
	get_item_stock_profile,
	validate_stock_availability,
)


VACCINE_DOCTYPE = "Veterinary Vaccine"
VACCINATION_RECORD_DOCTYPE = "Veterinary Vaccination Record"
VACCINATION_STATUSES = {"Draft", "Awaiting Payment", "Pending Administration", "Administered", "Cancelled"}
ADMINISTER_ROLES = {*DOCTOR_ROLES, ROLE_VETERINARY_NURSE, "VetEdge Nurse"}
DRAFT_CREATION_ROLES = {*ADMINISTER_ROLES, *FRONT_DESK_ROLES}
PAYMENT_OVERRIDE_ROLES = {*ELEVATED_ROLES, "Branch Manager", "VetEdge Branch Manager"}


@dataclass(frozen=True)
class VaccineDefaults:
	default_item: str | None = None
	default_next_due_days: int = 0
	default_validity_days: int = 0
	species: str | None = None
	is_active: bool = True


def validate_vaccine(doc) -> None:
	if not doc.vaccine_name:
		frappe.throw("Vaccine Name is required.", frappe.ValidationError)

	doc.vaccine_name = str(doc.vaccine_name).strip()
	if doc.vaccine_code:
		doc.vaccine_code = str(doc.vaccine_code).strip().upper()
	if cint(doc.get("default_validity_days")) < 0:
		frappe.throw("Default Validity Days cannot be negative.", frappe.ValidationError)
	if cint(doc.get("default_next_due_days")) < 0:
		frappe.throw("Default Next Due Days cannot be negative.", frappe.ValidationError)
	if doc.default_item:
		validate_sales_item(doc.default_item, "Vaccine Default Item", allow_stock=True)


def validate_vaccination_record(doc) -> None:
	ensure_vaccination_enabled()
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None

	validate_status(doc, previous)
	resolve_record_context(doc)
	set_vaccination_identity_fields(doc)
	validate_consultation_link(doc)
	validate_vaccine_applicability(doc)
	validate_branch_action_access(doc, previous)
	validate_action_roles(doc, previous)
	validate_administered_record_edit(doc, previous)
	validate_duplicate_same_day(doc)
	validate_stock_batch(doc)
	calculate_next_due_date(doc)


def ensure_vaccination_enabled() -> None:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return
	if not is_enabled("vaccination"):
		frappe.throw("Vaccination is not enabled in Veterinary Settings.", frappe.ValidationError)



def is_vaccination_payment_enforcement_enabled() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return False
	get_meta = getattr(frappe, "get_meta", None)
	if not get_meta:
		return False
	meta = get_meta("Veterinary Settings")
	if not meta.has_field("vaccination_requires_payment_before_administration"):
		return False
	return bool(
		frappe.db.get_single_value("Veterinary Settings", "vaccination_requires_payment_before_administration")
	)


def validate_status(doc, previous=None) -> None:
	if not doc.status:
		doc.status = "Draft"
	if doc.status not in VACCINATION_STATUSES:
		frappe.throw(f"Invalid vaccination status: {doc.status}", frappe.ValidationError)
	if previous and previous.status == "Cancelled" and doc.status != "Cancelled":
		frappe.throw("Cancelled vaccination records cannot be reopened.", frappe.ValidationError)
	if previous and previous.status == "Administered" and doc.status in {"Draft", "Awaiting Payment", "Pending Administration"}:
		frappe.throw("Administered vaccination records cannot be moved back to an earlier workflow state.", frappe.ValidationError)


def resolve_record_context(doc) -> None:
	if not doc.patient:
		frappe.throw("Patient is required for Vaccination Record.", frappe.ValidationError)
	if not doc.vaccine:
		frappe.throw("Vaccine is required for Vaccination Record.", frappe.ValidationError)

	patient = frappe.db.get_value(
		"Veterinary Patient",
		doc.patient,
		["primary_owner", "default_branch", "species"],
		as_dict=True,
	)
	if not patient:
		frappe.throw("Vaccination Record must reference a valid Veterinary Patient.", frappe.ValidationError)

	if doc.linked_consultation:
		consultation = frappe.db.get_value(
			"Veterinary Consultation",
			doc.linked_consultation,
			["patient", "primary_owner", "service_branch", "company", "consulting_practitioner"],
			as_dict=True,
		)
		if not consultation:
			frappe.throw("Linked Consultation must be a valid Veterinary Consultation.", frappe.ValidationError)
		if consultation.patient != doc.patient:
			frappe.throw("Linked Consultation must belong to the selected patient.", frappe.ValidationError)
		if not doc.primary_owner and consultation.primary_owner:
			doc.primary_owner = consultation.primary_owner
		if not doc.service_branch and consultation.service_branch:
			doc.service_branch = consultation.service_branch
		if not doc.company and consultation.company:
			doc.company = consultation.company

	if not doc.primary_owner:
		doc.primary_owner = patient.primary_owner
	if not doc.primary_owner:
		frappe.throw("Patient must have a linked owner before vaccination can be recorded.", frappe.ValidationError)
	if not doc.service_branch:
		doc.service_branch = patient.default_branch
	if not doc.service_branch:
		frappe.throw("Service Branch is required for Vaccination Record.", frappe.ValidationError)
	if not doc.company:
		doc.company = get_default_company()
	if doc.status == "Administered":
		if not doc.administered_on:
			doc.administered_on = now_datetime()
		if not doc.administered_by:
			doc.administered_by = get_current_user()


def set_vaccination_identity_fields(doc) -> None:
	doc.vaccination_id = doc.name or doc.get("vaccination_id") or ""

	patient_title = get_document_title("Veterinary Patient", doc.patient) or doc.patient
	vaccine_title = get_document_title(VACCINE_DOCTYPE, doc.vaccine) or doc.vaccine
	parts = [vaccine_title, patient_title]
	if doc.administered_on:
		parts.append(str(getdate(doc.administered_on)))
	elif doc.next_due_date:
		parts.append(f"Due {doc.next_due_date}")
	if doc.service_branch:
		parts.append(doc.service_branch)

	doc.vaccination_title = " - ".join(part for part in parts if part)


def validate_consultation_link(doc) -> None:
	if not doc.linked_consultation:
		return
	can_access_consultation(get_current_user(), doc.linked_consultation, raise_exception=True)


def validate_vaccine_applicability(doc) -> None:
	vaccine = get_vaccine_defaults(doc.vaccine)
	if not vaccine.is_active:
		frappe.throw(f"Vaccine {doc.vaccine} is inactive.", frappe.ValidationError)
	if not vaccine.species:
		return
	patient_species = frappe.db.get_value("Veterinary Patient", doc.patient, "species")
	if patient_species and patient_species != vaccine.species:
		frappe.throw(f"Vaccine {doc.vaccine} is only configured for Species {vaccine.species}.", frappe.ValidationError)


def validate_branch_action_access(doc, previous=None) -> None:
	user = get_current_user()
	if not user or user == "Guest":
		return
	if user_has_any_role(user, ELEVATED_ROLES):
		return
	if previous is None or doc.status != getattr(previous, "status", None) or doc.status == "Administered":
		require_vaccination_branch_access(user, doc.service_branch, context=doc)


def require_vaccination_branch_access(user: str | None, branch: str | None, context=None) -> None:
	can_access_branch_data(user, branch, raise_exception=True)
	if user_has_any_role(user, ELEVATED_ROLES):
		return
	assignments = get_assigned_branches(user)
	if frappe.db.exists("DocType", "Branch User Assignment") and (not assignments or branch not in assignments):
		frappe.throw(f"User {user} is not assigned to Branch {branch}.", frappe.PermissionError)


def validate_action_roles(doc, previous=None) -> None:
	user = get_current_user()
	if not user or user == "Guest":
		return
	if not is_internal_staff_user(user):
		frappe.throw("Vaccination actions are only available to clinic staff.", frappe.PermissionError)

	if previous is None and not user_has_any_role(user, DRAFT_CREATION_ROLES):
		frappe.throw("Only clinical staff or front desk can create vaccination records.", frappe.PermissionError)

	status_changed_to_administered = doc.status == "Administered" and (previous is None or previous.status != "Administered")
	if status_changed_to_administered:
		can_administer_vaccine(user, doc, raise_exception=True)
		enforce_vaccination_payment_before_administration(doc, user=user)


def can_administer_vaccine(user: str | None, doc=None, raise_exception: bool = False) -> bool:
	user = user or get_current_user()
	if not is_internal_staff_user(user):
		return _deny(raise_exception, "Vaccination administration is only available to clinic staff.")
	if not user_has_any_role(user, ADMINISTER_ROLES):
		return _deny(raise_exception, "Only a VetEdge Doctor or Nurse can administer vaccines.")
	if doc:
		require_vaccination_branch_access(user, doc.service_branch, context=doc)
	return True


def get_document_title(doctype: str, name: str | None) -> str | None:
	if not name:
		return None

	meta = frappe.get_meta(doctype)
	title_field = meta.get_title_field()
	if title_field and title_field != "name":
		return frappe.db.get_value(doctype, name, title_field)

	return name


def validate_administered_record_edit(doc, previous=None) -> None:
	if not previous or previous.status != "Administered":
		return
	if user_has_any_role(get_current_user(), ELEVATED_ROLES):
		return

	allowed_system_updates = {"linked_invoice", "stock_entry_reference"}
	changed = set(get_changed_fields(doc, previous))
	if changed - allowed_system_updates:
		frappe.throw("Only an administrator can modify an administered vaccination record.", frappe.PermissionError)


def get_changed_fields(doc, previous) -> list[str]:
	changed = []
	for field in doc.meta.fields:
		fieldname = field.fieldname
		if doc.get(fieldname) != previous.get(fieldname):
			changed.append(fieldname)
	return changed


def validate_duplicate_same_day(doc) -> None:
	if doc.status == "Cancelled" or not doc.patient or not doc.vaccine or not doc.administered_on:
		return
	filters = {
		"patient": doc.patient,
		"vaccine": doc.vaccine,
		"status": ["!=", "Cancelled"],
		"administered_on": ["between", [f"{getdate(doc.administered_on)} 00:00:00", f"{getdate(doc.administered_on)} 23:59:59"]],
	}
	if getattr(doc, "name", None):
		filters["name"] = ["!=", doc.name]
	if frappe.db.exists(VACCINATION_RECORD_DOCTYPE, filters):
		frappe.throw("This patient already has this vaccine recorded for the selected date.", frappe.ValidationError)


def validate_stock_batch(doc) -> None:
	vaccine = get_vaccine_defaults(doc.vaccine)
	if not doc.batch_no:
		if doc.expiry_date:
			doc.expiry_date = None
		return
	if not vaccine.default_item:
		frappe.throw("Batch No can only be set when the vaccine has a Default Item.", frappe.ValidationError)
	batch = frappe.db.get_value("Batch", doc.batch_no, ["item", "expiry_date", "disabled"], as_dict=True)
	if not batch or batch.item != vaccine.default_item:
		frappe.throw(f"Batch {doc.batch_no} is not valid for Item {vaccine.default_item}.", frappe.ValidationError)
	if cint(batch.disabled):
		frappe.throw(f"Batch {doc.batch_no} is disabled.", frappe.ValidationError)
	if batch.expiry_date and getdate(batch.expiry_date) <= getdate(doc.administered_on or now_datetime()):
		frappe.throw(f"Batch {doc.batch_no} expired on {batch.expiry_date}.", frappe.ValidationError)
	doc.expiry_date = batch.expiry_date or None


def calculate_next_due_date(doc) -> None:
	if doc.next_due_date or not doc.administered_on:
		return
	defaults = get_vaccine_defaults(doc.vaccine)
	default_days = defaults.default_next_due_days or defaults.default_validity_days
	if default_days:
		doc.next_due_date = add_days(getdate(doc.administered_on), default_days)


def get_vaccine_defaults(vaccine: str) -> VaccineDefaults:
	row = frappe.db.get_value(
		VACCINE_DOCTYPE,
		vaccine,
		["default_item", "default_next_due_days", "default_validity_days", "species", "is_active"],
		as_dict=True,
	)
	if not row:
		frappe.throw(f"Vaccine {vaccine} is not valid.", frappe.ValidationError)
	return VaccineDefaults(
		default_item=row.default_item,
		default_next_due_days=cint(row.default_next_due_days),
		default_validity_days=cint(row.default_validity_days),
		species=row.species,
		is_active=bool(cint(row.is_active)),
	)



def parse_vaccination_values(values: dict | str | None = None, **overrides) -> dict:
	parser = getattr(frappe, "parse_json", None)
	payload = parser(values) if parser and values is not None else values
	if payload in (None, ""):
		payload = {}
	payload = dict(payload or {})
	for key, value in overrides.items():
		if value is not None and key not in payload:
			payload[key] = value
	return payload



def vaccination_requires_payment_before_administration(doc) -> bool:
	settings = get_consultation_billing_settings()
	if doc.linked_consultation and settings.enabled and settings.requires_payment_before_treatment:
		return True
	vaccine = get_vaccine_defaults(doc.vaccine) if getattr(doc, "vaccine", None) else VaccineDefaults()
	return bool(vaccine.default_item and is_vaccination_payment_enforcement_enabled())



def enforce_vaccination_payment_before_administration(doc, user: str | None = None) -> None:
	if not vaccination_requires_payment_before_administration(doc):
		return
	user = user or get_current_user()
	if user_has_any_role(user, PAYMENT_OVERRIDE_ROLES):
		return
	if not doc.linked_invoice:
		frappe.throw(
			"Create and pay the vaccination invoice before administering this vaccine.",
			frappe.ValidationError,
		)
	invoice = frappe.get_doc("Sales Invoice", doc.linked_invoice)
	if invoice.docstatus == 2 or get_invoice_payment_status(invoice) != PAID_STATUS:
		frappe.throw(
			"Pay the vaccination invoice before administering this vaccine.",
			frappe.ValidationError,
		)



def get_vaccination_workflow_status(doc) -> str:
	if doc.status == "Cancelled":
		return "Cancelled"
	if doc.status == "Administered":
		return "Administered"
	if not doc.linked_invoice:
		return "Draft"
	invoice = frappe.get_doc("Sales Invoice", doc.linked_invoice)
	if invoice.docstatus == 2:
		return "Draft"
	if vaccination_requires_payment_before_administration(doc):
		if get_invoice_payment_status(invoice) != PAID_STATUS:
			return "Awaiting Payment"
		return "Pending Administration"
	return "Pending Administration"



def finalize_administered_vaccination(doc, create_invoice: int = 1, post_stock: int = 1) -> dict:
	calculate_next_due_date(doc)
	stock_entry = create_vaccination_stock_entry(doc) if cint(post_stock) else None
	if stock_entry:
		doc.stock_entry_reference = stock_entry
	invoice = create_vaccination_invoice(doc) if cint(create_invoice) else None
	if invoice:
		doc.linked_invoice = invoice

	doc.save()
	due_appointment = create_next_due_vaccination_appointment(doc)
	emit_notification_event(
		"vaccination_administered",
		doc.doctype,
		doc.name,
		{
			"patient": doc.patient,
			"vaccine": doc.vaccine,
			"branch": doc.service_branch,
			"administered_on": doc.administered_on,
			"next_due_date": doc.next_due_date,
			"linked_invoice": doc.linked_invoice,
			"stock_entry_reference": doc.stock_entry_reference,
			"due_appointment": due_appointment,
		},
	)
	return {
		"name": doc.name,
		"vaccination_record": doc.name,
		"status": doc.status,
		"next_due_date": doc.next_due_date,
		"linked_invoice": doc.linked_invoice,
		"stock_entry_reference": doc.stock_entry_reference,
		"due_appointment": due_appointment,
	}


@frappe.whitelist()
def create_vaccination_from_consultation(
	consultation: str,
	values: dict | str | None = None,
	vaccine: str | None = None,
	dose: str | None = None,
	route: str | None = None,
	notes: str | None = None,
	administered_on: str | None = None,
	next_due_date: str | None = None,
	create_invoice: int = 1,
	post_stock: int = 1,
) -> dict:
	require_internal_user()
	ensure_vaccination_enabled()
	if not consultation:
		frappe.throw("Consultation is required to create vaccination.", frappe.ValidationError)

	payload = parse_vaccination_values(
		values,
		vaccine=vaccine,
		dose=dose,
		route=route,
		notes=notes,
		administered_on=administered_on,
		next_due_date=next_due_date,
		create_invoice=create_invoice,
		post_stock=post_stock,
	)
	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation)
	can_access_consultation(get_current_user(), consultation, raise_exception=True)
	require_vaccination_branch_access(get_current_user(), consultation_doc.service_branch, context=consultation_doc)

	doc = frappe.get_doc(
		{
			"doctype": VACCINATION_RECORD_DOCTYPE,
			"patient": consultation_doc.patient,
			"primary_owner": consultation_doc.primary_owner,
			"service_branch": consultation_doc.service_branch,
			"company": consultation_doc.company,
			"linked_consultation": consultation_doc.name,
			"vaccine": payload.get("vaccine"),
			"dose": payload.get("dose"),
			"route": payload.get("route"),
			"notes": payload.get("notes"),
			"administered_on": payload.get("administered_on") or now_datetime(),
			"next_due_date": payload.get("next_due_date"),
			"status": "Draft",
		}
	)
	doc.insert(ignore_permissions=True)
	if cint(payload.get("create_invoice", 1)):
		invoice_result = create_or_update_vaccination_invoice(doc.name)
		if getattr(doc, "reload", None):
			doc.reload()
		return {
			"name": doc.name,
			"vaccination_record": doc.name,
			"status": invoice_result.get("status") or doc.status,
			"linked_invoice": invoice_result.get("invoice"),
			"next_due_date": doc.next_due_date,
		}
	return {
		"name": doc.name,
		"vaccination_record": doc.name,
		"status": doc.status,
		"linked_invoice": doc.linked_invoice,
		"next_due_date": doc.next_due_date,
	}


@frappe.whitelist()
def administer_vaccination(record: str, batch_no: str | None = None, create_invoice: int = 1, post_stock: int = 1) -> dict:
	require_internal_user()
	doc = frappe.get_doc(VACCINATION_RECORD_DOCTYPE, record)
	if doc.status not in {"Draft", "Awaiting Payment", "Pending Administration"}:
		frappe.throw("Only Draft, Awaiting Payment, or Pending Administration vaccination records can be administered.", frappe.ValidationError)
	can_administer_vaccine(get_current_user(), doc, raise_exception=True)
	enforce_vaccination_payment_before_administration(doc)

	if batch_no:
		doc.batch_no = batch_no
	doc.status = "Administered"
	doc.administered_by = get_current_user()
	doc.administered_on = doc.administered_on or now_datetime()
	return finalize_administered_vaccination(doc, create_invoice=create_invoice, post_stock=post_stock)


@frappe.whitelist()
def create_or_update_vaccination_invoice(record: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc(VACCINATION_RECORD_DOCTYPE, record)
	if doc.status == "Cancelled":
		frappe.throw("Cancelled vaccination records cannot be billed.", frappe.ValidationError)
	invoice_name = create_vaccination_invoice(doc)
	if invoice_name:
		doc.linked_invoice = invoice_name
	if doc.status != "Administered":
		doc.status = get_vaccination_workflow_status(doc)
	doc.save(ignore_permissions=True)
	return {
		"name": doc.name,
		"vaccination_record": doc.name,
		"invoice": doc.linked_invoice,
		"status": doc.status,
	}


def create_vaccination_invoice(doc) -> str | None:
	vaccine = get_vaccine_defaults(doc.vaccine)
	if not vaccine.default_item:
		return None

	if doc.linked_consultation:
		result = create_consultation_invoice(doc.linked_consultation, update_status=0)
		return result.get("invoice")

	cost_center = get_billing_cost_center(doc.service_branch, required=True)
	invoice_name = doc.linked_invoice if is_draft_sales_invoice(doc.linked_invoice) else None
	if invoice_name:
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if invoice.customer and invoice.customer != doc.primary_owner:
			frappe.throw("Linked Invoice customer does not match the vaccination owner.", frappe.ValidationError)
		invoice_name = ensure_vaccination_invoice_item(invoice, vaccine.default_item, cost_center)
	else:
		if doc.linked_invoice and is_active_sales_invoice(doc.linked_invoice):
			return doc.linked_invoice
		item = build_invoice_item(vaccine.default_item, 1, None, None, cost_center)
		invoice = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": doc.primary_owner,
				"company": doc.company or get_default_company(),
				"posting_date": getdate(doc.administered_on),
				"due_date": getdate(doc.administered_on),
				"items": [item],
				"remarks": f"Vaccination billing for {doc.name}",
			}
		)
		if frappe.get_meta("Sales Invoice").has_field("branch"):
			invoice.branch = doc.service_branch
		invoice.insert(ignore_permissions=True)
		invoice_name = invoice.name
	return invoice_name



def ensure_vaccination_invoice_item(invoice, item_code: str, cost_center: str) -> str:
	if invoice.docstatus == 2:
		return invoice.name

	item_payload = build_invoice_item(item_code, 1, None, None, cost_center)
	existing_row = next((row for row in (invoice.items or []) if row.item_code == item_code), None)
	if existing_row:
		existing_row.qty = item_payload["qty"]
		existing_row.uom = item_payload["uom"]
		existing_row.rate = item_payload["rate"]
		existing_row.amount = item_payload["amount"]
		existing_row.cost_center = item_payload["cost_center"]
	else:
		invoice.append("items", item_payload)

	invoice.save(ignore_permissions=True)
	return invoice.name



def create_next_due_vaccination_appointment(doc) -> str | None:
	if not doc.next_due_date or not is_appointment_creation_enabled():
		return None

	appointment_datetime = f"{getdate(doc.next_due_date)} 09:00:00"
	existing = frappe.get_all(
		"Veterinary Appointment",
		filters={
			"patient": doc.patient,
			"branch": doc.service_branch,
			"appointment_type": "Vaccination",
			"appointment_datetime": appointment_datetime,
			"status": ["not in", ["Cancelled", "No Show"]],
		},
		pluck="name",
		limit=1,
	)
	if existing:
		return existing[0]

	appointment = frappe.get_doc(
		{
			"doctype": "Veterinary Appointment",
			"patient": doc.patient,
			"primary_owner": doc.primary_owner,
			"branch": doc.service_branch,
			"practitioner": doc.administered_by,
			"appointment_datetime": appointment_datetime,
			"status": "Scheduled",
			"appointment_type": "Vaccination",
			"created_from": "Consultation" if doc.linked_consultation else "Manual",
			"notes": f"Vaccination due follow-up for {doc.vaccine} from {doc.name}",
		}
	)
	appointment.insert(ignore_permissions=True)
	emit_appointment_event(appointment, "appointment_created", previous_status=None)
	return appointment.name



def is_appointment_creation_enabled() -> bool:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return False
	return is_enabled("appointments")


def create_vaccination_stock_entry(doc) -> str | None:
	if doc.stock_entry_reference and is_active_stock_entry(doc.stock_entry_reference):
		return doc.stock_entry_reference

	vaccine = get_vaccine_defaults(doc.vaccine)
	if not vaccine.default_item:
		return None

	profile = get_item_stock_profile(vaccine.default_item)
	if not profile.is_stock_item:
		return None

	validate_stock_item_expiry_configuration(profile)
	warehouse = get_branch_dispensary_warehouse(doc.service_branch, company=doc.company, required=True)
	allocations = []
	if profile.has_batch_no:
		allocations = allocate_item_batches(
			item_code=vaccine.default_item,
			warehouse=warehouse,
			qty=1,
			posting_datetime=doc.administered_on,
			manual_batch_no=doc.batch_no,
		)
		if not doc.batch_no and allocations:
			doc.batch_no = allocations[0].batch_no
		if not doc.expiry_date and allocations:
			doc.expiry_date = allocations[0].expiry_date

	stock_rows = [
		{
			"item_code": vaccine.default_item,
			"qty": 1,
			"uom": profile.stock_uom,
			"batch_allocations": allocations,
		}
	]
	validate_stock_availability(stock_rows, warehouse, posting_datetime=get_datetime(doc.administered_on))
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"purpose": "Material Issue",
			"company": doc.company or get_default_company(),
			"from_warehouse": warehouse,
			"remarks": f"Vaccination stock issue for {doc.name}: {summarize_allocations(allocations) if allocations else vaccine.default_item}",
			"items": build_stock_entry_rows(
				items=stock_rows,
				warehouse=warehouse,
				company=doc.company or get_default_company(),
				use_serial_batch_fields=cint(frappe.get_single_value("Stock Settings", "use_serial_batch_fields")),
			),
		}
	)
	if frappe.get_meta("Stock Entry").has_field("branch"):
		entry.branch = doc.service_branch
	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry.name


def is_active_sales_invoice(invoice: str | None) -> bool:
	return bool(invoice and cint(frappe.db.get_value("Sales Invoice", invoice, "docstatus")) != 2)


def is_draft_sales_invoice(invoice: str | None) -> bool:
	return bool(invoice and cint(frappe.db.get_value("Sales Invoice", invoice, "docstatus")) == 0)



def sync_vaccination_workflow_status(record_name: str) -> None:
	record = frappe.get_doc(VACCINATION_RECORD_DOCTYPE, record_name)
	if record.status in {"Administered", "Cancelled"}:
		return
	status = get_vaccination_workflow_status(record)
	if status != record.status:
		frappe.db.set_value(VACCINATION_RECORD_DOCTYPE, record.name, "status", status, update_modified=False)



def update_vaccination_status_from_invoice(doc, method: str | None = None) -> None:
	for row in frappe.get_all(
		VACCINATION_RECORD_DOCTYPE,
		filters={"linked_invoice": doc.name},
		fields=["name"],
	):
		sync_vaccination_workflow_status(row.name)



def update_vaccination_status_from_payment_entry(doc, method: str | None = None) -> None:
	for reference in doc.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue
		invoice = frappe.get_doc("Sales Invoice", reference.reference_name)
		update_vaccination_status_from_invoice(invoice, method)


def is_active_stock_entry(stock_entry: str | None) -> bool:
	return bool(stock_entry and cint(frappe.db.get_value("Stock Entry", stock_entry, "docstatus")) != 2)


@frappe.whitelist()
def get_vaccination_history(patient: str, limit: int = 50, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
	require_internal_user()
	if not frappe.has_permission(VACCINATION_RECORD_DOCTYPE, "read"):
		frappe.throw("Not permitted to read Veterinary Vaccination Record.", frappe.PermissionError)
	filters = {"patient": patient, "status": ["!=", "Cancelled"]}
	if from_date and to_date:
		filters["administered_on"] = ["between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]]
	rows = frappe.get_all(
		VACCINATION_RECORD_DOCTYPE,
		filters=filters,
		fields=[
			"name",
			"vaccine",
			"administered_on",
			"service_branch",
			"administered_by",
			"next_due_date",
			"status",
			"linked_consultation",
			"linked_invoice",
			"stock_entry_reference",
			"dose",
			"route",
			"primary_owner",
		],
		order_by="administered_on desc, modified desc",
		limit=cint(limit) or 50,
	)
	invoice_names = [row.linked_invoice for row in rows if row.linked_invoice]
	invoice_map = {
		row.name: row
		for row in frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", invoice_names]} if invoice_names else {"name": ["in", [""]]},
			fields=["name", "status", "outstanding_amount", "grand_total"],
		)
	}
	user_names = [row.administered_by for row in rows if row.administered_by]
	user_map = {
		row.name: (row.full_name or row.name)
		for row in frappe.get_all(
			"User",
			filters={"name": ["in", user_names]} if user_names else {"name": ["in", [""]]},
			fields=["name", "full_name"],
		)
	}
	return [
		serialize_vaccination_history_row(row, invoice_map.get(row.linked_invoice), user_map.get(row.administered_by))
		for row in rows
	]


@frappe.whitelist()
def get_consultation_vaccinations(consultation: str, limit: int = 50) -> list[dict]:
	require_internal_user()
	if not frappe.has_permission(VACCINATION_RECORD_DOCTYPE, "read"):
		frappe.throw("Not permitted to read Veterinary Vaccination Record.", frappe.PermissionError)
	can_access_consultation(get_current_user(), consultation, raise_exception=True)
	rows = frappe.get_list(
		VACCINATION_RECORD_DOCTYPE,
		filters={"linked_consultation": consultation, "status": ["!=", "Cancelled"]},
		fields=[
			"name",
			"vaccine",
			"administered_on",
			"service_branch",
			"administered_by",
			"next_due_date",
			"status",
			"linked_consultation",
			"linked_invoice",
			"stock_entry_reference",
			"dose",
			"route",
			"primary_owner",
		],
		order_by="creation asc",
		limit=cint(limit) or 50,
	)
	invoice_names = [row.linked_invoice for row in rows if row.linked_invoice]
	invoice_map = {
		row.name: row
		for row in frappe.get_all(
			"Sales Invoice",
			filters={"name": ["in", invoice_names]} if invoice_names else {"name": ["in", [""]]},
			fields=["name", "status", "outstanding_amount", "grand_total"],
		)
	}
	user_names = [row.administered_by for row in rows if row.administered_by]
	user_map = {
		row.name: (row.full_name or row.name)
		for row in frappe.get_all(
			"User",
			filters={"name": ["in", user_names]} if user_names else {"name": ["in", [""]]},
			fields=["name", "full_name"],
		)
	}
	return [
		serialize_vaccination_history_row(row, invoice_map.get(row.linked_invoice), user_map.get(row.administered_by))
		for row in rows
	]



def serialize_vaccination_history_row(row, invoice=None, administered_by_name: str | None = None) -> dict:
	due_state = None
	if row.next_due_date:
		today = getdate()
		due_date = getdate(row.next_due_date)
		due_state = "Overdue" if due_date < today else "Due" if due_date <= add_days(today, 30) else "Upcoming"
	return {
		"type": "vaccination",
		"name": row.name,
		"timestamp": row.administered_on,
		"vaccine": row.vaccine,
		"dose": row.dose,
		"route": row.route,
		"service_branch": row.service_branch,
		"administered_by": row.administered_by,
		"administered_by_name": administered_by_name or row.administered_by,
		"next_due_date": row.next_due_date,
		"due_state": due_state,
		"status": row.status,
		"workflow_status": row.status,
		"linked_consultation": row.linked_consultation,
		"linked_invoice": row.linked_invoice,
		"billing_status": invoice.status if invoice else None,
		"invoice_outstanding_amount": invoice.outstanding_amount if invoice else None,
		"invoice_total": invoice.grand_total if invoice else None,
		"stock_entry_reference": row.stock_entry_reference,
		"primary_owner": row.primary_owner,
	}


def query_due_vaccinations(from_date: str | None = None, to_date: str | None = None, overdue_only: int = 0, limit: int = 100) -> list[dict]:
	return _get_due_vaccinations(from_date=from_date, to_date=to_date, overdue_only=overdue_only, limit=limit)


@frappe.whitelist()
def get_due_vaccinations(from_date: str | None = None, to_date: str | None = None, overdue_only: int = 0, limit: int = 100) -> list[dict]:
	require_internal_user()
	return _get_due_vaccinations(from_date=from_date, to_date=to_date, overdue_only=overdue_only, limit=limit)


def _get_due_vaccinations(from_date: str | None = None, to_date: str | None = None, overdue_only: int = 0, limit: int = 100) -> list[dict]:
	today = getdate()
	filters = {"status": "Administered", "next_due_date": ["is", "set"]}
	if cint(overdue_only):
		filters["next_due_date"] = ["<", today]
	elif from_date or to_date:
		filters["next_due_date"] = ["between", [getdate(from_date or today), getdate(to_date or add_days(today, 30))]]
	else:
		filters["next_due_date"] = ["between", [today, add_days(today, 30)]]
	rows = frappe.get_list(
		VACCINATION_RECORD_DOCTYPE,
		filters=filters,
		fields=["name", "patient", "primary_owner", "vaccine", "service_branch", "next_due_date"],
		order_by="next_due_date asc",
		limit=cint(limit) or 100,
	)
	for row in rows:
		row["due_state"] = "Overdue" if getdate(row.next_due_date) < today else "Due"
		row["days_until_due"] = (getdate(row.next_due_date) - today).days
	return rows


def emit_due_vaccination_events() -> None:
	for row in query_due_vaccinations(overdue_only=0, limit=500):
		event = "vaccination_overdue" if row.get("due_state") == "Overdue" else "vaccination_due_soon"
		emit_notification_event(event, VACCINATION_RECORD_DOCTYPE, row.name, dict(row))


def _deny(raise_exception: bool, message: str) -> bool:
	if raise_exception:
		frappe.throw(message, frappe.PermissionError)
	return False
