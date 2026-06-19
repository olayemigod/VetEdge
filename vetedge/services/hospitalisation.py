from __future__ import annotations

import frappe
from frappe.utils import cint, now, nowdate

from vetedge.services.billing import get_invoice_payment_status
from vetedge.services.payment_gate import (
	FULL_PAYMENT_REQUIRED,
	NO_PAYMENT_GATE,
	PARTIAL_PAYMENT_GATE,
	evaluate_invoice_payment_gate,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import get_default_company


SETTINGS_DOCTYPE = "Veterinary Settings"
HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
DISABLED_MESSAGE = "Veterinary Hospitalisation is not enabled for this clinic."
ACTIVE_HOSPITALISATION_STATUSES = {"Draft", "Admitted", "Under Care", "Ready for Discharge"}
DISCHARGE_ALLOWED_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}


def is_hospitalisation_enabled() -> bool:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return False

	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	if not meta.has_field("enable_veterinary_hospitalisation"):
		return False

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	return bool(cint(settings.get("enable_veterinary_hospitalisation")))


def assert_hospitalisation_enabled() -> None:
	if not is_hospitalisation_enabled():
		frappe.throw(DISABLED_MESSAGE, frappe.ValidationError)


def get_hospitalisation_payment_gate() -> str:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return PARTIAL_PAYMENT_GATE

	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	if not meta.has_field("hospitalisation_payment_gate"):
		return PARTIAL_PAYMENT_GATE

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	gate = settings.get("hospitalisation_payment_gate") or PARTIAL_PAYMENT_GATE
	if gate not in {FULL_PAYMENT_REQUIRED, PARTIAL_PAYMENT_GATE, NO_PAYMENT_GATE}:
		return PARTIAL_PAYMENT_GATE
	return gate


def validate_hospitalisation(doc) -> None:
	if doc.is_new():
		assert_hospitalisation_enabled()
	sync_hospitalisation_title(doc)
	normalize_hospitalisation_activities(doc)


def normalize_hospitalisation_activities(doc) -> None:
	for row in doc.get("activities") or []:
		if not row.get("performed_by"):
			row.performed_by = getattr(frappe.session, "user", None)

		if cint(row.get("billable")):
			if row.get("billing_status") in (None, "", "Not Billable"):
				row.billing_status = "Pending Charge"
		else:
			if row.get("billing_status") in (None, "", "Pending Charge"):
				row.billing_status = "Not Billable"

		if cint(row.get("stock_affecting")):
			if row.get("stock_status") in (None, "", "Not Applicable"):
				row.stock_status = "Pending"
		else:
			if row.get("stock_status") in (None, "", "Pending"):
				row.stock_status = "Not Applicable"


def sync_hospitalisation_title(doc) -> None:
	parts = [doc.get("patient"), doc.get("status"), doc.get("admission_datetime")]
	doc.hospitalisation_title = " - ".join(str(part) for part in parts if part)


@frappe.whitelist()
def create_hospitalisation_from_consultation(consultation_name: str) -> str:
	require_internal_user()
	assert_hospitalisation_enabled()
	consultation = frappe.get_doc("Veterinary Consultation", consultation_name)

	existing = get_active_hospitalisation_for_consultation(consultation.name)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": HOSPITALISATION_DOCTYPE,
			"patient": consultation.get("patient"),
			"customer": consultation.get("primary_owner"),
			"service_branch": consultation.get("service_branch"),
			"company": consultation.get("company"),
			"linked_consultation": consultation.name,
			"attending_veterinarian": consultation.get("consulting_practitioner"),
			"admission_reason": consultation.get("presenting_complaint") or "Admitted from consultation",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_active_hospitalisation_for_consultation(consultation_name: str) -> str | None:
	if not consultation_name or not frappe.db.exists("DocType", HOSPITALISATION_DOCTYPE):
		return None

	rows = frappe.get_all(
		HOSPITALISATION_DOCTYPE,
		filters={
			"linked_consultation": consultation_name,
			"status": ["not in", ["Cancelled", "Discharged"]],
		},
		fields=["name"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0].name if rows else None


@frappe.whitelist()
def create_or_link_hospitalisation_invoice(hospitalisation_name: str) -> str:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)

	if doc.get("sales_invoice") and frappe.db.exists("Sales Invoice", doc.sales_invoice):
		sync_invoice_status(doc)
		return doc.sales_invoice

	invoice = create_hospitalisation_invoice_doc(doc)
	doc.sales_invoice = invoice.name
	doc.invoice_status = get_invoice_payment_status(invoice)
	doc.save(ignore_permissions=True)
	return invoice.name


def create_hospitalisation_invoice_doc(doc):
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": doc.customer,
			"company": doc.company or get_default_company(),
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"items": build_hospitalisation_invoice_items(),
			"remarks": f"VetEdge hospitalisation invoice for {doc.name}",
		}
	)
	apply_hospitalisation_invoice_defaults(doc, invoice)
	invoice.insert(ignore_permissions=True, ignore_mandatory=True)
	return invoice


def build_hospitalisation_invoice_items() -> list[dict]:
	item_code = get_default_hospitalisation_item()
	if not item_code:
		return []
	return [{"item_code": item_code, "qty": 1}]


def get_default_hospitalisation_item() -> str | None:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return None
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	for fieldname in ("default_hospitalisation_item", "hospitalisation_item", "default_hospitalisation_admission_item"):
		if meta.has_field(fieldname):
			value = frappe.get_single(SETTINGS_DOCTYPE).get(fieldname)
			if value and frappe.db.exists("Item", value):
				return value
	return None


def apply_hospitalisation_invoice_defaults(doc, invoice) -> None:
	invoice_meta = frappe.get_meta("Sales Invoice")
	if doc.service_branch and invoice_meta.has_field("branch"):
		invoice.branch = doc.service_branch
	for fieldname in ("hospitalisation", "veterinary_hospitalisation", "vetedge_hospitalisation"):
		if invoice_meta.has_field(fieldname):
			invoice.set(fieldname, doc.name)
			break


def sync_invoice_status(doc) -> None:
	if not doc.get("sales_invoice") or not frappe.db.exists("Sales Invoice", doc.sales_invoice):
		doc.invoice_status = "Not Invoiced"
		doc.save(ignore_permissions=True)
		return
	invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice)
	doc.invoice_status = get_invoice_payment_status(invoice)
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def check_hospitalisation_payment_gate(hospitalisation_name: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	result = evaluate_hospitalisation_payment_gate(doc)
	update_payment_gate_fields(doc, result)
	return result


def evaluate_hospitalisation_payment_gate(doc) -> dict:
	gate = get_hospitalisation_payment_gate()
	invoice_name = doc.get("sales_invoice")
	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		return {
			"gate": gate,
			"can_proceed": False,
			"status": "Blocked",
			"message": "A submitted Sales Invoice is required before hospitalisation care can proceed.",
		}

	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	return evaluate_invoice_payment_gate(invoice, gate, "hospitalisation")


def update_payment_gate_fields(doc, result: dict) -> None:
	doc.payment_gate_status = result.get("status") or ("Allowed" if result.get("can_proceed") else "Blocked")
	doc.payment_gate_message = result.get("message")
	if doc.get("sales_invoice") and frappe.db.exists("Sales Invoice", doc.sales_invoice):
		doc.invoice_status = get_invoice_payment_status(frappe.get_doc("Sales Invoice", doc.sales_invoice))
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def admit_hospitalisation(hospitalisation_name: str) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	create_or_link_hospitalisation_invoice(doc.name)
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	result = evaluate_hospitalisation_payment_gate(doc)
	update_payment_gate_fields(doc, result)

	if not result.get("can_proceed"):
		return result

	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	doc.status = "Admitted" if doc.status == "Draft" else "Under Care"
	doc.admitted_by = frappe.session.user
	doc.save(ignore_permissions=True)
	result["hospitalisation"] = doc.name
	result["status"] = doc.payment_gate_status
	return result


@frappe.whitelist()
def discharge_hospitalisation(hospitalisation_name: str, discharge_summary: str | None = None) -> str:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	if doc.status not in DISCHARGE_ALLOWED_STATUSES:
		frappe.throw("Only admitted hospitalisations can be discharged.", frappe.ValidationError)

	doc.status = "Discharged"
	doc.discharged_by = frappe.session.user
	doc.discharge_datetime = now()
	if discharge_summary is not None:
		doc.discharge_summary = discharge_summary
	doc.save(ignore_permissions=True)
	return doc.name
