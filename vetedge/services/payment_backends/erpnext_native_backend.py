from __future__ import annotations

import frappe
from frappe.utils import flt


def initiate(context) -> dict:
	if not frappe.db.exists("DocType", "Payment Request"):
		frappe.throw("ERPNext Payment Request is not available on this site.", frappe.ValidationError)

	gateway_account = get_payment_gateway_account(context.company)
	payment_request = get_or_create_payment_request(context.invoice, gateway_account)
	if not payment_request.payment_url:
		frappe.throw(
			"Payment Request was created, but no payment URL was generated. Check the Payment Gateway Account setup.",
			frappe.ValidationError,
		)

	return {
		"success": True,
		"action": "redirect",
		"backend_mode": "erpnext_native",
		"payment_provider": "erpnext_native",
		"payment_reference": payment_request.name,
		"payment_status_snapshot": payment_request.status,
		"redirect_url": payment_request.payment_url,
		"amount": flt(payment_request.grand_total),
		"currency": payment_request.currency,
		"message": "Payment request created. Redirecting to payment page.",
		"creates_payment_entry": True,
		"backend_payload": {
			"backend_mode": "erpnext_native",
			"payment_request": payment_request.name,
			"reference_doctype": payment_request.reference_doctype,
			"reference_name": payment_request.reference_name,
		},
	}


def get_payment_status(reference: str) -> dict:
	if not frappe.db.exists("Payment Request", reference):
		return {
			"reference": reference,
			"backend_mode": "erpnext_native",
			"payment_status_snapshot": "not_found",
		}

	doc = frappe.get_doc("Payment Request", reference)
	return {
		"reference": reference,
		"backend_mode": "erpnext_native",
		"payment_status_snapshot": doc.status,
		"amount": flt(doc.grand_total),
		"currency": doc.currency,
		"redirect_url": doc.payment_url,
	}


def get_or_create_payment_request(invoice_doc, gateway_account: dict):
	existing = frappe.db.get_value(
		"Payment Request",
		{
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice_doc.name,
			"docstatus": ["<", 2],
			"status": ["not in", ["Paid", "Cancelled"]],
		},
		"name",
		order_by="creation desc",
	)
	if existing:
		payment_request = frappe.get_doc("Payment Request", existing)
		if payment_request.docstatus == 0:
			payment_request.flags.ignore_permissions = True
			payment_request.submit()
		elif not payment_request.payment_url and getattr(payment_request, "set_payment_request_url", None):
			payment_request.set_payment_request_url()
			payment_request.save(ignore_permissions=True)
		return payment_request

	email_to = get_customer_payment_email(invoice_doc.customer) or frappe.session.user
	payment_request = frappe.get_doc(
		{
			"doctype": "Payment Request",
			"payment_request_type": "Inward",
			"payment_gateway_account": gateway_account.name,
			"payment_gateway": gateway_account.payment_gateway,
			"payment_account": gateway_account.payment_account,
			"payment_channel": gateway_account.get("payment_channel") or "Email",
			"reference_doctype": "Sales Invoice",
			"reference_name": invoice_doc.name,
			"party_type": "Customer",
			"party": invoice_doc.customer,
			"party_name": invoice_doc.get("customer_name"),
			"company": invoice_doc.company,
			"currency": invoice_doc.currency,
			"party_account_currency": invoice_doc.get("party_account_currency") or invoice_doc.currency,
			"grand_total": flt(invoice_doc.outstanding_amount),
			"outstanding_amount": flt(invoice_doc.outstanding_amount),
			"email_to": email_to,
			"subject": f"Payment Request for {invoice_doc.name}",
			"message": gateway_account.get("message") or f"Please make payment for invoice {invoice_doc.name}.",
			"mute_email": 1,
		}
	)
	payment_request.flags.ignore_permissions = True
	payment_request.insert(ignore_permissions=True)
	payment_request.submit()
	return payment_request


def get_payment_gateway_account(company: str) -> dict:
	gateway_account = frappe.db.get_value(
		"Payment Gateway Account",
		{"is_default": 1, "company": company},
		["name", "payment_gateway", "payment_account", "payment_channel", "message"],
		as_dict=True,
	)
	if not gateway_account:
		frappe.throw(
			"Set a default Payment Gateway Account for the invoice company before enabling live portal payments.",
			frappe.ValidationError,
		)
	if not gateway_account.payment_gateway or not gateway_account.payment_account:
		frappe.throw(
			"Default Payment Gateway Account must have a Payment Gateway and Payment Account.",
			frappe.ValidationError,
		)
	return gateway_account


def get_customer_payment_email(customer: str) -> str | None:
	email = frappe.db.get_value("Customer", customer, "email_id")
	if email:
		return email

	if frappe.db.exists("DocType", "Portal User"):
		return frappe.db.get_value(
			"Portal User",
			{"parenttype": "Customer", "parent": customer},
			"user",
		)

	return None
