from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.utils import cint, flt, nowdate

from vetedge.services.branding import get_clinic_brand_name
from vetedge.services.dispensary import get_consultation_ready_status
from vetedge.services.notifications import emit_notification_event
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import get_billing_cost_center, get_default_company


SETTINGS_DOCTYPE = "Veterinary Settings"
PAID_STATUS = "Paid"
UNPAID_STATUS = "Unpaid"
PARTLY_PAID_STATUS = "Partly Paid"
CANCELLED_STATUS = "Cancelled"


@dataclass(frozen=True)
class ConsultationBillingSettings:
	enabled: bool
	consultation_item: str | None
	allow_doctor_collect_payment: bool
	requires_payment_before_treatment: bool
	enable_treatment_billing: bool
	enforce_cost_center: bool


def validate_consultation_billing_settings(settings) -> None:
	if not cint(settings.get("enable_consultation_billing")):
		return

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
	)


@frappe.whitelist()
def create_consultation_invoice(consultation: str) -> dict:
	require_internal_user()
	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation)
	settings = get_consultation_billing_settings()
	validate_consultation_invoice_request(consultation_doc, settings)

	cost_center = get_billing_cost_center(consultation_doc.service_branch, required=True)
	items = build_consultation_invoice_items(consultation_doc, settings, cost_center)
	if not items:
		frappe.throw("No billable consultation or treatment items found.", frappe.ValidationError)

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

	if consultation_doc.service_branch and frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = consultation_doc.service_branch
	if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = cost_center

	invoice.insert(ignore_permissions=True)
	update_consultation_after_invoice_created(consultation_doc, invoice, settings)
	emit_invoice_created_notifications(consultation_doc, invoice, settings)

	return {
		"consultation": consultation_doc.name,
		"invoice": invoice.name,
		"status": get_consultation_status_after_invoice_created(consultation_doc, settings),
	}


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
	if not settings.consultation_item:
		frappe.throw("Consultation Item is required when consultation billing is enabled.", frappe.ValidationError)
	if doc.linked_invoice and is_active_sales_invoice(doc.linked_invoice):
		frappe.throw("This consultation already has an active linked Sales Invoice.", frappe.ValidationError)


def is_active_sales_invoice(invoice: str) -> bool:
	docstatus = frappe.db.get_value("Sales Invoice", invoice, "docstatus")
	return docstatus is not None and cint(docstatus) != 2


def build_consultation_invoice_items(
	consultation_doc,
	settings: ConsultationBillingSettings,
	cost_center: str,
) -> list[dict]:
	items = [build_invoice_item(settings.consultation_item, 1, None, None, cost_center)]

	if settings.enable_treatment_billing:
		for row in consultation_doc.get("planned_treatments") or []:
			items.append(build_invoice_item(row.item, row.qty, row.get("uom"), row.get("rate"), cost_center))

	return items


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


def update_consultation_after_invoice_created(doc, invoice, settings: ConsultationBillingSettings) -> None:
	status = get_consultation_status_after_invoice_created(doc, settings)
	values = {
		"linked_invoice": invoice.name,
		"payment_status": UNPAID_STATUS,
	}
	if status and doc.status not in {"Completed", "Cancelled"}:
		values["status"] = status

	frappe.db.set_value("Veterinary Consultation", doc.name, values, update_modified=False)


def get_consultation_status_after_invoice_created(doc, settings: ConsultationBillingSettings) -> str:
	if settings.requires_payment_before_treatment:
		return "Awaiting Payment"
	if doc.status in {"Draft", "In Progress", "Awaiting Payment"}:
		return get_consultation_ready_status(doc)
	return doc.status


def consultation_requires_invoice_before_progress(doc, target_status: str | None = None) -> bool:
	settings = get_consultation_billing_settings()
	if not settings.enabled:
		return False

	target_status = target_status or doc.status
	if target_status not in {"Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed"}:
		return False

	return bool(settings.consultation_item or (settings.enable_treatment_billing and (doc.get("planned_treatments") or [])))


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

	if doc.payment_status == PAID_STATUS:
		return

	frappe.throw(
		"Consultation payment is required before treatment can proceed.",
		frappe.ValidationError,
	)


def emit_invoice_created_notifications(doc, invoice, settings: ConsultationBillingSettings) -> None:
	payload = {
		"consultation": doc.name,
		"invoice": invoice.name,
		"customer": invoice.customer,
		"branch": doc.service_branch,
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
	if not consultation_doc.linked_invoice:
		frappe.throw("Create a consultation invoice before collecting payment.", frappe.ValidationError)

	invoice = frappe.get_doc("Sales Invoice", consultation_doc.linked_invoice)
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
	consultations = frappe.get_all(
		"Veterinary Consultation",
		filters={"linked_invoice": doc.name},
		fields=["name", "status", "payment_status"],
	)
	for consultation in consultations:
		update_single_consultation_payment_status(consultation, doc)


def update_consultation_payment_status_from_payment_entry(doc, method: str | None = None) -> None:
	for reference in doc.get("references") or []:
		if reference.reference_doctype != "Sales Invoice" or not reference.reference_name:
			continue
		invoice = frappe.get_doc("Sales Invoice", reference.reference_name)
		update_consultation_payment_status_from_invoice(invoice, method)


def update_single_consultation_payment_status(consultation, invoice) -> None:
	new_payment_status = get_invoice_payment_status(invoice)
	values = {"payment_status": new_payment_status}
	consultation_doc = None

	if new_payment_status == PAID_STATUS and consultation.status == "Awaiting Payment":
		consultation_doc = frappe.get_doc("Veterinary Consultation", consultation.name)
		values["status"] = get_consultation_ready_status(consultation_doc)

	frappe.db.set_value("Veterinary Consultation", consultation.name, values, update_modified=False)

	if new_payment_status == PAID_STATUS and consultation.payment_status != PAID_STATUS:
		emit_notification_event(
			"payment_received",
			"Sales Invoice",
			invoice.name,
			{
				"consultation": consultation.name,
				"invoice": invoice.name,
				"customer": invoice.customer,
				"branch": frappe.db.get_value("Veterinary Consultation", consultation.name, "service_branch"),
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
