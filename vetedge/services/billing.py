from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.utils import cint, flt, nowdate

from vetedge.services.branding import get_clinic_brand_name
from vetedge.services.dispensary import get_consultation_ready_status
from vetedge.services.lab import get_consultation_lab_billing_items, mark_consultation_lab_orders_invoiced
from vetedge.services.notifications import emit_notification_event
from vetedge.services.permissions import (
	ELEVATED_ROLES,
	ROLE_BRANCH_MANAGER,
	can_access_consultation,
	can_initiate_payment,
	get_current_user,
	get_invoice_access_diagnostic,
	user_has_any_role,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import get_billing_cost_center, get_default_company


SETTINGS_DOCTYPE = "Veterinary Settings"
PAID_STATUS = "Paid"
UNPAID_STATUS = "Unpaid"
PARTLY_PAID_STATUS = "Partly Paid"
CANCELLED_STATUS = "Cancelled"
CONSULTATION_INVOICE_REFERENCE_DOCTYPE = "Consultation Invoice Reference"
CONSULTATION_BILLING_SOURCE_DOCTYPE = "Consultation Billing Source"
CONSULTATION_INVOICE_REFERENCE_FIELD = "consultation_invoices"
CONSULTATION_BILLING_SOURCE_FIELD = "consultation_billing_sources"


@dataclass(frozen=True)
class ConsultationBillingSettings:
	enabled: bool
	consultation_item: str | None
	allow_doctor_collect_payment: bool
	requires_payment_before_treatment: bool
	enable_treatment_billing: bool
	enforce_cost_center: bool
	auto_add_default_consultation_billing_item: bool = True
	allow_editing_consultation_billing_item: bool = True


def validate_consultation_billing_settings(settings) -> None:
	if not cint(settings.get("enable_consultation_billing")):
		return

	if cint(settings.get("auto_add_default_consultation_billing_item", 1)):
		validate_sales_item(settings.get("consultation_item"), "Consultation Item", allow_stock=False)


def validate_sales_item(item_code: str | None, label: str, allow_stock: bool = True) -> None:
	if not item_code:
		frappe.throw(f"{label} is required when consultation billing is enabled.", frappe.ValidationError)

	item = frappe.db.get_value("Item", item_code, ["disabled", "is_sales_item", "is_stock_item"], as_dict=True)
	if not item:
		frappe.throw(f"{label} must be a valid Item.", frappe.ValidationError)
	if item.disabled:
		frappe.throw(f"{label} cannot be a disabled Item.", frappe.ValidationError)
	if not item.is_sales_item:
		frappe.throw(f"{label} must be a sales Item.", frappe.ValidationError)
	if not allow_stock and item.is_stock_item:
		frappe.throw(f"{label} must be a non-stock service Item.", frappe.ValidationError)


def get_consultation_billing_settings() -> ConsultationBillingSettings:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return ConsultationBillingSettings(False, None, False, False, False, True)

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	meta = frappe.get_meta(SETTINGS_DOCTYPE)

	def get(fieldname: str, default=None):
		return settings.get(fieldname) if meta.has_field(fieldname) else default

	return ConsultationBillingSettings(
		enabled=bool(settings.get("enable_vetedge") and get("enable_consultation_billing", 0)),
		consultation_item=get("consultation_item"),
		allow_doctor_collect_payment=bool(get("allow_doctor_collect_payment", 0)),
		requires_payment_before_treatment=bool(get("consultation_requires_payment_before_treatment", 0)),
		enable_treatment_billing=bool(settings.get("enable_vetedge") and get("enable_treatment_billing", 0)),
		enforce_cost_center=bool(get("enforce_cost_center_on_billing", 1)),
		auto_add_default_consultation_billing_item=bool(get("auto_add_default_consultation_billing_item", 1)),
		allow_editing_consultation_billing_item=bool(get("allow_editing_consultation_billing_item", 1)),
	)


def is_consultation_billing_enabled() -> bool:
	return bool(get_consultation_billing_settings().enabled)


def should_auto_add_default_consultation_item(settings: ConsultationBillingSettings | None = None) -> bool:
	settings = settings or get_consultation_billing_settings()
	return bool(
		getattr(settings, "enabled", False)
		and getattr(settings, "auto_add_default_consultation_billing_item", True)
		and getattr(settings, "consultation_item", None)
	)


def can_edit_default_consultation_billing_item(settings: ConsultationBillingSettings | None = None) -> bool:
	settings = settings or get_consultation_billing_settings()
	return bool(getattr(settings, "allow_editing_consultation_billing_item", True))


@frappe.whitelist()
def create_consultation_invoice(consultation: str, update_status: int = 1) -> dict:
	require_internal_user()
	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation)
	can_access_consultation(frappe.session.user, consultation, raise_exception=True)
	settings = get_consultation_billing_settings()
	validate_consultation_invoice_request(consultation_doc, settings)
	if use_billing_core_for_source("Veterinary Consultation"):
		from vetedge.services.billing_core import sync_source_to_billing_session

		result = sync_source_to_billing_session("Veterinary Consultation", consultation_doc.name)
		invoice_name = result.get("invoice")
		if invoice_name:
			update_consultation_after_billing_core_sync(consultation_doc, invoice_name, settings, update_status=update_status)
		return {
			"consultation": consultation_doc.name,
			"invoice": invoice_name,
			"is_draft_update": not bool(result.get("created")),
			"status": frappe.db.get_value("Veterinary Consultation", consultation_doc.name, "status") or consultation_doc.status,
			"billing_session": result.get("session"),
		}


	cost_center = get_billing_cost_center(consultation_doc.service_branch, required=True)
	draft_invoice_name = get_active_consultation_invoice_name(consultation_doc)
	items, billed_sources = build_consultation_invoice_payload(
		consultation_doc,
		settings,
		cost_center,
		draft_invoice_name=draft_invoice_name,
	)
	if not items:
		frappe.throw("No billable consultation, treatment, lab, or vaccination items found.", frappe.ValidationError)

	if draft_invoice_name:
		invoice = update_existing_consultation_invoice(consultation_doc, draft_invoice_name, items, cost_center)
	else:
		invoice = create_new_consultation_invoice(consultation_doc, items, cost_center)

	update_consultation_after_invoice_created(
		consultation_doc,
		invoice,
		settings,
		billed_sources=billed_sources,
		update_status=update_status,
	)
	if not draft_invoice_name:
		emit_invoice_created_notifications(consultation_doc, invoice, settings)

	return {
		"consultation": consultation_doc.name,
		"invoice": invoice.name,
		"is_draft_update": bool(draft_invoice_name),
		"status": consultation_doc.status,
	}


@frappe.whitelist()
def get_invoice_access_summary(invoice: str) -> dict:
	require_internal_user()
	diagnostic = get_invoice_access_diagnostic(frappe.session.user, invoice)
	if not diagnostic.get("allowed"):
		frappe.throw(diagnostic.get("message"), frappe.PermissionError)

	fields = [
		"name",
		"customer",
		"posting_date",
		"due_date",
		"status",
		"outstanding_amount",
		"grand_total",
		"currency",
	]
	invoice_doc = frappe.get_doc("Sales Invoice", invoice)
	if frappe.get_meta("Sales Invoice").has_field("branch"):
		fields.append("branch")

	invoice_row = frappe._dict({fieldname: invoice_doc.get(fieldname) for fieldname in fields})

	return {
		**invoice_row,
		"can_open_full_form": bool(diagnostic.get("can_open_full_form")),
	}


def use_billing_core_for_source(source_doctype: str) -> bool:
	try:
		from vetedge.services.billing_core import is_billing_sessions_enabled

		return is_billing_sessions_enabled()
	except Exception:
		return False


def update_consultation_after_billing_core_sync(doc, invoice_name: str, settings: ConsultationBillingSettings, update_status: int = 1) -> None:
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	doc = get_latest_consultation_doc(doc)
	values = {
		"linked_invoice": invoice.name,
		"payment_status": get_invoice_payment_status(invoice),
	}
	status = get_consultation_status_after_invoice_created(doc, settings) if cint(update_status) else None
	if status and doc.status not in {"Completed", "Cancelled"}:
		values["status"] = status
	for fieldname, value in values.items():
		setattr(doc, fieldname, value)
	if getattr(doc, "save", None):
		doc.save()
	else:
		frappe.db.set_value("Veterinary Consultation", doc.name, values, update_modified=False)


@frappe.whitelist()
def get_consultation_invoice_summaries(consultation: str) -> list[dict]:
	require_internal_user()
	can_access_consultation(frappe.session.user, consultation, raise_exception=True)
	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation)
	summaries = []
	for invoice_name in get_consultation_invoice_names(consultation_doc):
		try:
			summaries.append(get_invoice_access_summary(invoice_name))
		except frappe.PermissionError:
			continue
	return summaries


def validate_consultation_invoice_request(doc, settings: ConsultationBillingSettings) -> None:
	if not settings.enabled:
		frappe.throw("Consultation billing is not enabled.", frappe.ValidationError)
	if doc.status in {"Completed", "Cancelled"}:
		frappe.throw(f"Cannot create invoice for a {doc.status} consultation.", frappe.ValidationError)
	if not doc.patient:
		frappe.throw("Consultation must have a patient before billing.", frappe.ValidationError)
	if not doc.primary_owner:
		frappe.throw("Consultation must have an owner/customer before billing.", frappe.ValidationError)
	if not doc.service_branch:
		frappe.throw("Consultation must have a service branch before billing.", frappe.ValidationError)
	if getattr(settings, "auto_add_default_consultation_billing_item", True) and not settings.consultation_item:
		frappe.throw("Consultation Item is required when consultation billing is enabled.", frappe.ValidationError)


def is_active_sales_invoice(invoice: str) -> bool:
	docstatus = frappe.db.get_value("Sales Invoice", invoice, "docstatus")
	return docstatus is not None and cint(docstatus) != 2


def build_consultation_invoice_payload(
	consultation_doc,
	settings: ConsultationBillingSettings,
	cost_center: str,
	draft_invoice_name: str | None = None,
) -> tuple[list[dict], list[dict]]:
	items: list[dict] = []
	sources: list[dict] = []

	if should_auto_add_default_consultation_item(settings) and should_include_consultation_fee(consultation_doc, draft_invoice_name):
		items.append(build_invoice_item(settings.consultation_item, 1, None, None, cost_center))
		sources.append(
			build_consultation_billing_source(
				source_type="Consultation Fee",
				source_name=consultation_doc.name,
				sales_invoice=draft_invoice_name,
				item_code=settings.consultation_item,
			)
		)

	if settings.enable_treatment_billing:
		for row in get_unbilled_treatment_rows(consultation_doc, draft_invoice_name):
			items.append(build_invoice_item(row.item, row.qty, row.get("uom"), row.get("rate"), cost_center))
			sources.append(
				build_consultation_billing_source(
					source_type="Treatment",
					source_name=get_consultation_treatment_source_name(row),
					sales_invoice=draft_invoice_name,
					item_code=row.item,
				)
			)

	lab_items, lab_sources = get_consultation_lab_billing_items(
		consultation_doc,
		cost_center,
		invoice_name=draft_invoice_name,
	)
	items.extend(lab_items)
	sources.extend(lab_sources)

	vaccination_items, vaccination_sources = get_consultation_vaccination_billing_items(
		consultation_doc,
		cost_center,
		draft_invoice_name=draft_invoice_name,
	)
	items.extend(vaccination_items)
	sources.extend(vaccination_sources)

	return items, sources


def build_invoice_item(
	item_code: str,
	qty,
	uom: str | None,
	rate,
	cost_center: str,
) -> dict:
	validate_sales_item(item_code, "Billable Item", allow_stock=True)
	item_defaults = frappe.db.get_value("Item", item_code, ["stock_uom", "standard_rate"], as_dict=True) or {}
	qty = flt(qty) or 1
	rate = flt(rate) if rate not in (None, "") else flt(item_defaults.get("standard_rate"))
	if rate < 0:
		frappe.throw("Billable item rate cannot be negative.", frappe.ValidationError)

	return {
		"item_code": item_code,
		"qty": qty,
		"uom": uom or item_defaults.get("stock_uom"),
		"rate": rate,
		"amount": qty * rate,
		"cost_center": cost_center,
	}


def update_consultation_after_invoice_created(
	doc,
	invoice,
	settings: ConsultationBillingSettings,
	billed_sources: list[dict] | None = None,
	update_status: int = 1,
) -> None:
	doc = get_latest_consultation_doc(doc)
	status = get_consultation_status_after_invoice_created(doc, settings) if cint(update_status) else None
	values = {
		"linked_invoice": invoice.name,
		"payment_status": get_invoice_payment_status(invoice),
	}
	if status and doc.status not in {"Completed", "Cancelled"}:
		values["status"] = status

	for fieldname, value in values.items():
		setattr(doc, fieldname, value)

	replace_child_rows(
		doc,
		CONSULTATION_INVOICE_REFERENCE_FIELD,
		build_consultation_invoice_reference_rows(doc, invoice),
	)
	replace_child_rows(
		doc,
		CONSULTATION_BILLING_SOURCE_FIELD,
		build_consultation_billing_source_rows(doc, invoice, billed_sources or []),
	)

	if getattr(doc, "save", None):
		doc.save(ignore_permissions=True, ignore_version=True)
	else:
		frappe.db.set_value("Veterinary Consultation", doc.name, values, update_modified=False)

	mark_consultation_lab_orders_invoiced(doc.name, invoice.name)


def get_consultation_status_after_invoice_created(doc, settings: ConsultationBillingSettings) -> str:
	if doc.status == "Draft":
		return "In Progress"
	if settings.requires_payment_before_treatment:
		return "Awaiting Payment"
	if doc.status in {"In Progress", "Awaiting Payment"}:
		return get_consultation_ready_status(doc)
	return doc.status


def consultation_requires_invoice_before_progress(doc, target_status: str | None = None) -> bool:
	settings = get_consultation_billing_settings()
	if not settings.enabled:
		return False

	target_status = target_status or doc.status
	if target_status not in {"Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed"}:
		return False

	if get_consultation_invoice_names(doc):
		return True

	if should_auto_add_default_consultation_item(settings) or (settings.enable_treatment_billing and (doc.get("planned_treatments") or [])):
		return True

	for row in frappe.get_all(
		"Veterinary Vaccination Record",
		filters={"linked_consultation": doc.name, "status": ["!=", "Cancelled"]},
		fields=["vaccine"],
		limit=50,
	):
		if frappe.db.get_value("Veterinary Vaccine", row.vaccine, "default_item"):
			return True

	return False


def validate_consultation_invoice_before_progress(doc, target_status: str | None = None) -> None:
	if not consultation_requires_invoice_before_progress(doc, target_status):
		return

	if doc.linked_invoice and is_active_sales_invoice(doc.linked_invoice):
		return

	frappe.throw(
		"Create the consultation invoice before moving this consultation to the next treatment stage.",
		frappe.ValidationError,
	)


def validate_consultation_payment_before_treatment(doc, target_status: str | None = None) -> None:
	settings = get_consultation_billing_settings()
	if not settings.enabled or not settings.requires_payment_before_treatment:
		return

	target_status = target_status or doc.status
	if target_status not in {"Pending Dispensary", "Ready for Treatment", "Completed"}:
		return

	if not consultation_requires_invoice_before_progress(doc, target_status):
		return

	if user_has_any_role(get_current_user(), {*ELEVATED_ROLES, ROLE_BRANCH_MANAGER, "VetEdge Branch Manager"}):
		return

	invoice_names = get_consultation_invoice_names(doc)
	if doc.get("linked_invoice") and doc.linked_invoice not in invoice_names:
		invoice_names.append(doc.linked_invoice)
	if not invoice_names:
		frappe.throw(
			"Create and pay all consultation-related invoices before treatment can proceed.",
			frappe.ValidationError,
		)

	for invoice_name in invoice_names:
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if invoice.docstatus == 2:
			continue
		if get_invoice_payment_status(invoice) != PAID_STATUS:
			frappe.throw(
				"All consultation-related invoices, including vaccination invoices, must be fully paid before treatment can proceed.",
				frappe.ValidationError,
			)


def emit_invoice_created_notifications(doc, invoice, settings: ConsultationBillingSettings) -> None:
	payload = {
		"consultation": doc.name,
		"invoice": invoice.name,
		"patient": doc.patient,
		"patient_name": frappe.db.get_value("Veterinary Patient", doc.patient, "patient_name") if doc.patient else None,
		"primary_owner": doc.primary_owner,
		"customer": invoice.customer,
		"branch": doc.service_branch,
		"amount": invoice.grand_total,
		"requires_payment_before_treatment": settings.requires_payment_before_treatment,
		"allow_doctor_collect_payment": settings.allow_doctor_collect_payment,
	}
	emit_notification_event("invoice_created", "Sales Invoice", invoice.name, payload)

	if settings.requires_payment_before_treatment:
		emit_notification_event("consultation_awaiting_payment", doc.doctype, doc.name, payload)
		if not settings.allow_doctor_collect_payment:
			emit_notification_event("accounts_action_required", doc.doctype, doc.name, payload)
	elif get_consultation_status_after_invoice_created(doc, settings) == "Pending Dispensary":
		emit_notification_event("consultation_sent_to_dispensary", doc.doctype, doc.name, payload)


@frappe.whitelist()
def create_payment_entry_from_consultation(consultation: str, mode_of_payment: str | None = None) -> dict:
	require_internal_user()
	settings = get_consultation_billing_settings()
	if not settings.allow_doctor_collect_payment:
		frappe.throw("Doctor payment collection is not enabled.", frappe.PermissionError)

	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation)
	active_invoice = get_collectible_consultation_invoice_name(consultation_doc)
	if active_invoice:
		can_initiate_payment(frappe.session.user, active_invoice, mode="internal", raise_exception=True)
	if not active_invoice:
		frappe.throw("Create a consultation invoice before collecting payment.", frappe.ValidationError)

	invoice = frappe.get_doc("Sales Invoice", active_invoice)
	if invoice.docstatus != 1:
		frappe.throw("Submit the Sales Invoice before creating a Payment Entry.", frappe.ValidationError)
	if flt(invoice.outstanding_amount) <= 0:
		frappe.throw("The linked Sales Invoice has no outstanding amount.", frappe.ValidationError)

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	payment_entry = get_payment_entry("Sales Invoice", invoice.name)
	if mode_of_payment:
		payment_entry.mode_of_payment = mode_of_payment
	payment_entry.insert(ignore_permissions=True)

	emit_notification_event(
		"payment_initiated",
		"Payment Entry",
		payment_entry.name,
		{
			"consultation": consultation_doc.name,
			"invoice": invoice.name,
			"customer": invoice.customer,
			"outstanding_amount": invoice.outstanding_amount,
		},
	)

	return {
		"consultation": consultation_doc.name,
		"invoice": invoice.name,
		"payment_entry": payment_entry.name,
	}


def update_consultation_payment_status_from_invoice(doc, method: str | None = None) -> None:
	consultation_names = get_consultation_names_for_invoice(doc.name)
	consultations = [
		frappe._dict(
			name=name,
			status=frappe.db.get_value("Veterinary Consultation", name, "status"),
			payment_status=frappe.db.get_value("Veterinary Consultation", name, "payment_status"),
		)
		for name in consultation_names
	]
	for consultation in consultations:
		sync_consultation_invoice_reference_from_invoice(consultation.name, doc)
		update_single_consultation_payment_status(consultation, doc)


def update_consultation_payment_status_from_payment_entry(doc, method: str | None = None) -> None:
	for reference in doc.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue
		invoice = frappe.get_doc("Sales Invoice", reference.reference_name)
		update_consultation_payment_status_from_invoice(invoice, method)


def update_single_consultation_payment_status(consultation, invoice) -> None:
	from vetedge.services.billing_core import get_consultation_payment_status
	new_payment_status = get_consultation_payment_status(get_consultation_payment_source_status(invoice))
	values = {"payment_status": new_payment_status}
	consultation_doc = None

	if new_payment_status == PAID_STATUS and consultation.status == "Awaiting Payment":
		consultation_doc = frappe.get_doc("Veterinary Consultation", consultation.name)
		values["status"] = get_consultation_ready_status(consultation_doc)
	elif consultation.status in {"In Progress", "Awaiting Payment"} and can_advance_consultation_after_submitted_invoice(invoice):
		consultation_doc = frappe.get_doc("Veterinary Consultation", consultation.name)
		values["status"] = get_post_invoice_consultation_status(consultation_doc)

	frappe.db.set_value("Veterinary Consultation", consultation.name, values, update_modified=False)

	if new_payment_status == PAID_STATUS and consultation.payment_status != PAID_STATUS:
		if not consultation_doc:
			consultation_doc = frappe.get_doc("Veterinary Consultation", consultation.name)
		emit_notification_event(
			"payment_received",
			"Sales Invoice",
			invoice.name,
			{
				"consultation": consultation.name,
				"invoice": invoice.name,
				"patient": consultation_doc.patient,
				"patient_name": frappe.db.get_value("Veterinary Patient", consultation_doc.patient, "patient_name")
				if consultation_doc.patient
				else None,
				"primary_owner": consultation_doc.primary_owner,
				"customer": invoice.customer,
				"branch": consultation_doc.service_branch,
				"amount": invoice.grand_total,
			},
		)
		if values.get("status") == "Pending Dispensary":
			emit_notification_event(
				"consultation_sent_to_dispensary",
				"Veterinary Consultation",
				consultation.name,
				{"invoice": invoice.name, "payment_status": new_payment_status},
			)
		else:
			emit_notification_event(
				"consultation_ready_for_treatment",
				"Veterinary Consultation",
				consultation.name,
				{"invoice": invoice.name, "payment_status": new_payment_status},
			)


def can_advance_consultation_after_submitted_invoice(invoice) -> bool:
	if cint(invoice.docstatus) != 1:
		return False

	from vetedge.services.payment_gate import NO_PAYMENT_GATE, PARTIAL_PAYMENT_GATE, get_consultation_payment_gate, has_valid_payment

	gate = get_consultation_payment_gate()
	if gate == NO_PAYMENT_GATE:
		return True
	if gate == PARTIAL_PAYMENT_GATE:
		return has_valid_payment(invoice.name)
	return False


def get_post_invoice_consultation_status(doc) -> str:
	return get_consultation_ready_status(doc)


def get_invoice_payment_status(invoice) -> str:
	if invoice.docstatus == 2:
		return CANCELLED_STATUS
	if invoice.docstatus != 1:
		return UNPAID_STATUS
	if flt(invoice.outstanding_amount) <= 0:
		return PAID_STATUS
	if flt(invoice.outstanding_amount) < flt(invoice.grand_total):
		return PARTLY_PAID_STATUS
	return UNPAID_STATUS


def get_consultation_payment_source_status(invoice) -> str:
	if cint(getattr(invoice, "docstatus", 0)) == 0:
		return getattr(invoice, "status", None) or "Draft"
	return get_invoice_payment_status(invoice)


def create_new_consultation_invoice(consultation_doc, items: list[dict], cost_center: str):
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": consultation_doc.primary_owner,
			"company": consultation_doc.company or get_default_company(),
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"items": items,
			"remarks": f"{get_clinic_brand_name()} consultation billing for {consultation_doc.name}",
		}
	)
	apply_consultation_invoice_defaults(consultation_doc, invoice, cost_center)
	invoice.insert(ignore_permissions=True)
	return invoice


def update_existing_consultation_invoice(consultation_doc, invoice_name: str, items: list[dict], cost_center: str):
	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	if invoice.docstatus != 0:
		frappe.throw("Only draft consultation invoices can be updated.", frappe.ValidationError)
	invoice.customer = consultation_doc.primary_owner
	invoice.company = consultation_doc.company or get_default_company()
	invoice.posting_date = nowdate()
	invoice.due_date = nowdate()
	invoice.remarks = f"{get_clinic_brand_name()} consultation billing for {consultation_doc.name}"
	invoice.set("items", items)
	apply_consultation_invoice_defaults(consultation_doc, invoice, cost_center)
	invoice.save(ignore_permissions=True)
	return invoice


def apply_consultation_invoice_defaults(consultation_doc, invoice, cost_center: str) -> None:
	if consultation_doc.service_branch and frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = consultation_doc.service_branch
	if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = cost_center


def get_active_consultation_invoice_name(doc) -> str | None:
	for invoice_name in get_consultation_invoice_names(doc):
		if frappe.db.get_value("Sales Invoice", invoice_name, "docstatus") == 0:
			return invoice_name
	if doc.get("linked_invoice") and frappe.db.get_value("Sales Invoice", doc.linked_invoice, "docstatus") == 0:
		return doc.linked_invoice
	return None


def get_collectible_consultation_invoice_name(doc) -> str | None:
	for invoice_name in get_consultation_invoice_names(doc):
		invoice = frappe.db.get_value(
			"Sales Invoice",
			invoice_name,
			["docstatus", "outstanding_amount"],
			as_dict=True,
		)
		if invoice and invoice.docstatus == 1 and flt(invoice.outstanding_amount) > 0:
			return invoice_name
	if doc.get("linked_invoice"):
		return doc.linked_invoice
	return None


def get_consultation_invoice_names(doc) -> list[str]:
	names = []
	for row in doc.get(CONSULTATION_INVOICE_REFERENCE_FIELD) or []:
		if row.sales_invoice and row.sales_invoice not in names:
			names.append(row.sales_invoice)
	if doc.get("linked_invoice") and doc.linked_invoice not in names:
		names.append(doc.linked_invoice)
	return names


def should_include_consultation_fee(doc, draft_invoice_name: str | None = None) -> bool:
	return not is_consultation_source_billed(doc, "Consultation Fee", doc.name, draft_invoice_name)


def get_unbilled_treatment_rows(doc, draft_invoice_name: str | None = None) -> list:
	rows = []
	for row in doc.get("planned_treatments") or []:
		if not row.item:
			continue
		if is_consultation_source_billed(doc, "Treatment", get_consultation_treatment_source_name(row), draft_invoice_name):
			continue
		rows.append(row)
	return rows


def get_consultation_treatment_source_name(row) -> str:
	return row.get("name") or f"{row.item}:{row.get('idx') or 0}"



def get_consultation_vaccination_billing_items(doc, cost_center: str, draft_invoice_name: str | None = None) -> tuple[list[dict], list[dict]]:
	items: list[dict] = []
	sources: list[dict] = []
	rows = frappe.get_all(
		"Veterinary Vaccination Record",
		filters={"linked_consultation": doc.name, "status": ["!=", "Cancelled"]},
		fields=["name", "vaccine"],
		order_by="creation asc",
	)
	for row in rows:
		if is_consultation_source_billed(doc, "Vaccination", row.name, draft_invoice_name):
			continue
		item_code = frappe.db.get_value("Veterinary Vaccine", row.vaccine, "default_item")
		if not item_code:
			continue
		items.append(build_invoice_item(item_code, 1, None, None, cost_center))
		sources.append(
			build_consultation_billing_source(
				source_type="Vaccination",
				source_name=row.name,
				sales_invoice=draft_invoice_name,
				item_code=item_code,
			)
		)
	return items, sources


def is_consultation_source_billed(doc, source_type: str, source_name: str, draft_invoice_name: str | None = None) -> bool:
	for row in doc.get(CONSULTATION_BILLING_SOURCE_FIELD) or []:
		if row.source_type != source_type or row.source_name != source_name:
			continue
		if draft_invoice_name and row.sales_invoice == draft_invoice_name:
			return False
		if cint(row.get("invoice_docstatus")) == 2:
			continue
		return True
	return False


def build_consultation_billing_source(source_type: str, source_name: str, sales_invoice: str | None, item_code: str | None = None) -> dict:
	return {
		"source_type": source_type,
		"source_name": source_name,
		"sales_invoice": sales_invoice,
		"item_code": item_code,
	}


def build_consultation_invoice_reference_rows(doc, invoice) -> list[dict]:
	rows = []
	for row in doc.get(CONSULTATION_INVOICE_REFERENCE_FIELD) or []:
		if row.sales_invoice == invoice.name:
			continue
		rows.append(
			{
				"sales_invoice": row.sales_invoice,
				"invoice_status": row.invoice_status,
				"invoice_docstatus": row.invoice_docstatus,
				"posting_date": row.posting_date,
				"currency": row.currency,
				"grand_total": row.grand_total,
				"outstanding_amount": row.outstanding_amount,
			}
		)
	rows.append(build_consultation_invoice_reference(invoice))
	return rows


def build_consultation_invoice_reference(invoice) -> dict:
	from vetedge.services.billing_core import get_consultation_payment_status
	return {
		"sales_invoice": invoice.name,
		"invoice_status": get_consultation_payment_status(invoice.status),
		"invoice_docstatus": invoice.docstatus,
		"posting_date": invoice.posting_date,
		"currency": invoice.currency,
		"grand_total": invoice.grand_total,
		"outstanding_amount": invoice.outstanding_amount,
	}


def build_consultation_billing_source_rows(doc, invoice, billed_sources: list[dict]) -> list[dict]:
	from vetedge.services.billing_core import get_consultation_payment_status
	rows = []
	for row in doc.get(CONSULTATION_BILLING_SOURCE_FIELD) or []:
		if row.sales_invoice == invoice.name:
			continue
		rows.append(
			{
				"source_type": row.source_type,
				"source_name": row.source_name,
				"sales_invoice": row.sales_invoice,
				"invoice_docstatus": row.invoice_docstatus,
				"invoice_status": row.invoice_status,
				"item_code": row.item_code,
			}
		)
	for source in billed_sources:
		rows.append(
			{
				**source,
				"sales_invoice": invoice.name,
				"invoice_docstatus": invoice.docstatus,
				"invoice_status": get_consultation_payment_status(invoice.status),
			}
		)
	return rows


def replace_child_rows(doc, fieldname: str, rows: list[dict]) -> None:
	new_rows = [frappe._dict(row) for row in rows]
	setter = getattr(doc, "set", None)
	if callable(setter):
		doc.set(fieldname, new_rows)
	else:
		doc[fieldname] = new_rows


def get_consultation_names_for_invoice(invoice_name: str) -> list[str]:
	names = []
	if frappe.db.exists("DocType", CONSULTATION_INVOICE_REFERENCE_DOCTYPE):
		for row in frappe.get_all(
			CONSULTATION_INVOICE_REFERENCE_DOCTYPE,
			filters={"sales_invoice": invoice_name},
			fields=["parent"],
		):
			if row.parent and row.parent not in names:
				names.append(row.parent)

	for row in frappe.get_all(
		"Veterinary Consultation",
		filters={"linked_invoice": invoice_name},
		fields=["name"],
	):
		if row.name not in names:
			names.append(row.name)
	return names


def sync_consultation_invoice_reference_from_invoice(consultation_name: str, invoice) -> None:
	if not consultation_name or not frappe.db.exists("Veterinary Consultation", consultation_name):
		return
	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation_name)
	replace_child_rows(
		consultation_doc,
		CONSULTATION_INVOICE_REFERENCE_FIELD,
		build_consultation_invoice_reference_rows(consultation_doc, invoice),
	)
	replace_child_rows(
		consultation_doc,
		CONSULTATION_BILLING_SOURCE_FIELD,
		update_consultation_billing_source_statuses(consultation_doc, invoice),
	)
	if consultation_doc.get("linked_invoice") == invoice.name:
		from vetedge.services.billing_core import get_consultation_payment_status
		consultation_doc.payment_status = get_consultation_payment_status(get_consultation_payment_source_status(invoice))
	if getattr(consultation_doc, "save", None):
		consultation_doc.save(ignore_permissions=True, ignore_version=True)


def get_latest_consultation_doc(doc):
	if isinstance(doc, str):
		return frappe.get_doc("Veterinary Consultation", doc)

	name = getattr(doc, "name", None) or doc.get("name")
	doctype = getattr(doc, "doctype", None) or doc.get("doctype")
	exists = getattr(getattr(frappe, "db", None), "exists", None)
	if doctype == "Veterinary Consultation" and name and (not callable(exists) or exists("Veterinary Consultation", name)):
		return frappe.get_doc("Veterinary Consultation", name)
	return doc


def update_consultation_billing_source_statuses(doc, invoice) -> list[dict]:
	from vetedge.services.billing_core import get_consultation_payment_status
	rows = []
	for row in doc.get(CONSULTATION_BILLING_SOURCE_FIELD) or []:
		rows.append(
			{
				"source_type": row.source_type,
				"source_name": row.source_name,
				"sales_invoice": row.sales_invoice,
				"invoice_docstatus": invoice.docstatus if row.sales_invoice == invoice.name else row.invoice_docstatus,
				"invoice_status": get_consultation_payment_status(invoice.status) if row.sales_invoice == invoice.name else row.invoice_status,
				"item_code": row.item_code,
			}
		)
	return rows
