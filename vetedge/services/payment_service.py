from __future__ import annotations

import frappe
from frappe.utils import flt

from vetedge.services.notifications import emit_notification_event
from vetedge.services.portal_access import get_owner_context, get_portal_settings, validate_owner_invoice_access


SUPPORTED_PAYMENT_PROVIDERS = {"Stub", "ERPNext Payment Request"}


@frappe.whitelist()
def initiate_invoice_payment(invoice_name: str, provider: str | None = None) -> dict:
	owner_context = get_owner_context()
	settings = get_portal_settings()
	if not settings["enable_portal_payments"]:
		frappe.throw("Portal payments are not enabled.", frappe.PermissionError)

	invoice = validate_portal_invoice_payment_eligibility(invoice_name, owner_context)
	provider = provider or settings.get("portal_payment_provider_mode") or "Stub"
	if provider not in SUPPORTED_PAYMENT_PROVIDERS:
		frappe.throw(f"Unsupported payment provider mode: {provider}", frappe.ValidationError)

	response = build_payment_initiation_payload(invoice, provider)
	emit_notification_event(
		event="payment_initiated",
		reference_doctype="Sales Invoice",
		reference_name=invoice.name,
		payload={
			"customer": invoice.customer,
			"outstanding_amount": invoice.outstanding_amount,
			"provider": provider,
		},
	)
	return response


def validate_portal_invoice_payment_eligibility(invoice_name: str, owner_context: dict | None = None) -> dict:
	owner_context = owner_context or get_owner_context()
	invoice = validate_owner_invoice_access(invoice_name, owner_context)

	if invoice.docstatus != 1:
		frappe.throw("Only submitted Sales Invoices can be paid from the portal.", frappe.ValidationError)

	if flt(invoice.outstanding_amount) <= 0:
		frappe.throw("This Sales Invoice has no outstanding amount.", frappe.ValidationError)

	return invoice


def build_payment_initiation_payload(invoice: dict, provider: str) -> dict:
	payload = {
		"invoice": invoice.name,
		"customer": invoice.customer,
		"amount": flt(invoice.outstanding_amount),
		"currency": invoice.currency,
		"provider": provider,
		"status": "payment_initiation_prepared",
		"creates_payment_entry": False,
	}

	if provider == "Stub":
		payload.update(
			{
				"next_action": "configure_payment_gateway",
				"message": "Payment ownership and eligibility are validated. Configure a gateway before collecting live payments.",
			}
		)
	else:
		payload.update(
			{
				"next_action": "create_erpnext_payment_request",
				"message": "ERPNext Payment Request binding is reserved for the gateway setup step.",
			}
		)

	return payload


def handle_payment_callback(*args, **kwargs) -> dict:
	return {
		"handled": False,
		"message": "Payment callback handling is a provider-specific Phase 5+ integration point.",
	}
