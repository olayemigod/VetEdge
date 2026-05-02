from __future__ import annotations

from importlib import import_module

import frappe
from frappe.utils import flt, now_datetime

from vetedge.services.notifications import emit_notification_event
from vetedge.services.permissions import can_initiate_payment
from vetedge.services.portal_access import get_owner_context, get_portal_settings, validate_owner_invoice_access


DEFAULT_PAYMENT_BACKEND_MODE = "stub"
SUPPORTED_PAYMENT_BACKEND_MODES = {
	"stub": "vetedge.services.payment_backends.stub_backend",
	"erpnext_native": "vetedge.services.payment_backends.erpnext_native_backend",
	"processedge_core": "vetedge.services.payment_backends.processedge_core_backend",
}
LEGACY_PROVIDER_TO_BACKEND_MODE = {
	"Stub": "stub",
	"ERPNext Payment Request": "erpnext_native",
	"ProcessEdge Core Payment": "processedge_core",
}


@frappe.whitelist()
def initiate_invoice_payment(invoice_name: str, source_context: dict | None = None) -> dict:
	return initiate_payment(
		invoice_name=invoice_name,
		access_context={"mode": "owner", "owner_context": get_owner_context()},
		source_context=source_context or {"source": "owner_portal"},
	)


def initiate_payment(
	invoice_name: str,
	access_context: dict | None = None,
	source_context: dict | None = None,
	backend_mode: str | None = None,
) -> dict:
	settings = get_portal_settings()
	if not settings["enable_portal_payments"]:
		frappe.throw("Portal payments are not enabled.", frappe.PermissionError)

	resolved_backend_mode = resolve_payment_backend_mode(settings, backend_mode)
	invoice = validate_invoice_payable(invoice_name, access_context)
	context = prepare_payment_initiation_context(
		invoice=invoice,
		backend_mode=resolved_backend_mode,
		source_context=source_context,
		access_context=access_context,
	)
	response = get_backend(resolved_backend_mode).initiate(context)
	result = normalize_payment_response(response, context)

	emit_notification_event(
		event_key="payment_initiated",
		reference_doctype="Sales Invoice",
		reference_name=invoice.name,
		payload={
			"customer": invoice.customer,
			"invoice": invoice.name,
			"outstanding_amount": invoice.outstanding_amount,
			"backend_mode": resolved_backend_mode,
			"payment_reference": result.get("payment_reference"),
			"source": (source_context or {}).get("source"),
		},
	)
	return result


def validate_invoice_payable(invoice_name: str, access_context: dict | None = None):
	access_context = access_context or {"mode": "owner", "owner_context": get_owner_context()}
	mode = access_context.get("mode") or "owner"

	if mode == "owner":
		owner_context = access_context.get("owner_context") or get_owner_context()
		can_initiate_payment(getattr(frappe.session, "user", None), invoice_name, mode="owner", raise_exception=True)
		invoice = validate_owner_invoice_access(invoice_name, owner_context)
	else:
		invoice = frappe.db.get_value(
			"Sales Invoice",
			invoice_name,
			["name", "customer", "outstanding_amount", "currency", "docstatus"],
			as_dict=True,
		)
		if not invoice:
			frappe.throw("Sales Invoice not found.", frappe.PermissionError)
		if mode == "guest_registration" and invoice.name != access_context.get("allowed_invoice"):
			frappe.throw("This payment session is not allowed for the requested invoice.", frappe.PermissionError)
		can_initiate_payment(getattr(frappe.session, "user", None), invoice_name, mode="internal", raise_exception=True)

	if invoice.docstatus != 1:
		frappe.throw("Only submitted Sales Invoices can be paid.", frappe.ValidationError)

	if flt(invoice.outstanding_amount) <= 0:
		frappe.throw("This Sales Invoice has no outstanding amount.", frappe.ValidationError)

	return frappe.get_doc("Sales Invoice", invoice.name)


def prepare_payment_initiation_context(
	invoice,
	backend_mode: str,
	source_context: dict | None = None,
	access_context: dict | None = None,
) -> frappe._dict:
	source_context = source_context or {}
	access_context = access_context or {}
	return frappe._dict(
		{
			"invoice": invoice,
			"reference_doctype": "Sales Invoice",
			"invoice_name": invoice.name,
			"customer": invoice.customer,
			"amount": flt(invoice.outstanding_amount),
			"currency": invoice.currency,
			"company": invoice.company,
			"backend_mode": backend_mode,
			"source_context": source_context,
			"access_context": access_context,
			"payment_reference": None,
			"payment_provider": backend_mode,
			"payment_initiated_on": now_datetime(),
			"payment_status_snapshot": "pending_initiation",
		}
	)


def get_payment_status(reference: str, backend_mode: str | None = None) -> dict:
	resolved_backend_mode = resolve_payment_backend_mode(get_portal_settings(), backend_mode)
	return get_backend(resolved_backend_mode).get_payment_status(reference)


def normalize_payment_response(response: dict | None, context: frappe._dict) -> dict:
	response = response or {}
	return {
		"success": bool(response.get("success", True)),
		"invoice": context.invoice_name,
		"customer": context.customer,
		"amount": flt(response.get("amount", context.amount)),
		"currency": response.get("currency", context.currency),
		"backend_mode": context.backend_mode,
		"payment_provider": response.get("payment_provider", context.payment_provider),
		"payment_reference": response.get("payment_reference"),
		"payment_initiated_on": response.get("payment_initiated_on", context.payment_initiated_on),
		"payment_status_snapshot": response.get(
			"payment_status_snapshot",
			context.payment_status_snapshot,
		),
		"action": response.get("action", "message"),
		"redirect_url": response.get("redirect_url"),
		"message": response.get("message") or "Payment initiation prepared.",
		"creates_payment_entry": bool(response.get("creates_payment_entry", False)),
		"backend_payload": response.get("backend_payload"),
	}


def resolve_payment_backend_mode(settings: dict | None = None, backend_mode: str | None = None) -> str:
	settings = settings or get_portal_settings()
	mode = (
		backend_mode
		or settings.get("payment_backend_mode")
		or LEGACY_PROVIDER_TO_BACKEND_MODE.get(settings.get("portal_payment_provider_mode"))
		or DEFAULT_PAYMENT_BACKEND_MODE
	)
	mode = LEGACY_PROVIDER_TO_BACKEND_MODE.get(mode, mode)
	if mode not in SUPPORTED_PAYMENT_BACKEND_MODES:
		frappe.throw(f"Unsupported payment backend mode: {mode}", frappe.ValidationError)
	return mode


def get_backend(mode: str):
	if mode not in SUPPORTED_PAYMENT_BACKEND_MODES:
		frappe.throw(f"Unsupported payment backend mode: {mode}", frappe.ValidationError)
	module_path = SUPPORTED_PAYMENT_BACKEND_MODES[mode]
	return import_module(module_path)


def handle_payment_callback(*args, **kwargs) -> dict:
	return {
		"handled": False,
		"message": "Payment callback handling belongs to the configured backend integration.",
	}
