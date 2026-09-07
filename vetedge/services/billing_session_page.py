from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, flt

from vetedge.services.billing_center import (
	BILLING_SESSION_DOCTYPE,
	_branch_scope,
	_company_currency,
	_decorate_patient_names,
	_require_billing_center_access,
)

NO_BRANCH_SENTINEL = "__vetedge_no_permitted_branch__"


@frappe.whitelist()
def get_billing_session_detail(name: str) -> dict:
	"""Return one permission- and branch-safe Billing Session for EdgeSuite detail.

	The Veterinary Billing Session DocType remains authoritative. This endpoint is
	read-only and exists only to present that record inside the VetEdge shell.
	"""
	user = _require_billing_center_access()
	session_name = cstr(name or "").strip()
	if not session_name:
		frappe.throw(_("Billing Session is required."), frappe.ValidationError)

	branches, restricted = _branch_scope(user, None)
	filters: dict = {"name": session_name}
	if restricted:
		filters["branch"] = ["in", branches or [NO_BRANCH_SENTINEL]]

	rows = frappe.get_list(
		BILLING_SESSION_DOCTYPE,
		filters=filters,
		fields=[
			"name",
			"customer",
			"animal",
			"company",
			"branch",
			"status",
			"payment_gate_mode",
			"current_draft_invoice",
			"latest_invoice",
			"total_charges",
			"total_invoiced",
			"total_paid",
			"outstanding_amount",
			"payment_status",
			"source_context_doctype",
			"source_context_name",
			"created_from_doctype",
			"created_from_name",
			"creation",
			"modified",
		],
		limit_page_length=1,
	)
	if not rows:
		frappe.throw(_("Billing Session was not found or is not permitted."), frappe.PermissionError)

	row = _decorate_patient_names(rows)[0]
	session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
	charges = []
	for charge in session.get("charges") or []:
		charges.append(
			{
				"source_doctype": charge.get("source_doctype"),
				"source_name": charge.get("source_name"),
				"item_code": charge.get("item_code"),
				"item_name": charge.get("item_name") or charge.get("item_code"),
				"description": charge.get("description"),
				"qty": flt(charge.get("qty")),
				"uom": charge.get("uom"),
				"rate": flt(charge.get("rate")),
				"amount": flt(charge.get("amount")),
				"invoice": charge.get("invoice"),
				"billing_status": charge.get("billing_status"),
			}
		)

	row["charges"] = charges
	row["currency"] = _company_currency(row.get("company"))
	row["capabilities"] = {
		"sales_invoice": bool(frappe.has_permission("Sales Invoice", "read")),
	}
	row["boundary"] = _(
		"This EdgeSuite page is a read-only view of the authoritative Veterinary Billing Session. "
		"ERPNext accounting documents remain authoritative and open in their native accounting workflows."
	)
	return row
