from __future__ import annotations

import hashlib
import hmac
import json

import frappe
from frappe.utils import cint, flt


HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
QA_ENABLED_KEY = "vetedge_qa_inspection_enabled"
QA_TOKEN_KEY = "vetedge_qa_inspection_token"
QA_TOKEN_HEADER = "X-ProcessEdge-QA-Token"
RATE_LIMIT_PER_MINUTE = 60
ALLOWED_INSPECTIONS = {
	"hospitalisation_charges",
	"hospitalisation_activities",
	"related_invoice_summary",
	"stock_posting_summary",
	"payment_gate_evidence",
}


def _request_header(name: str) -> str:
	request = getattr(getattr(frappe, "local", None), "request", None)
	headers = getattr(request, "headers", None)
	if not headers:
		return ""
	return str(headers.get(name) or "")


def _remote_address() -> str:
	request = getattr(getattr(frappe, "local", None), "request", None)
	return str(getattr(request, "remote_addr", None) or "unknown")


def _assert_qa_environment() -> None:
	if not cint(frappe.conf.get(QA_ENABLED_KEY)):
		frappe.throw("VetEdge QA inspection is not enabled on this site.", frappe.PermissionError)


def _assert_service_token() -> str:
	expected = str(frappe.conf.get(QA_TOKEN_KEY) or "")
	provided = _request_header(QA_TOKEN_HEADER)
	if not expected or not provided or not hmac.compare_digest(expected, provided):
		frappe.throw("Invalid VetEdge QA inspection credential.", frappe.PermissionError)
	return provided


def _rate_limit(token: str) -> None:
	fingerprint = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
	key = f"vetedge:qa-inspection:{fingerprint}:{_remote_address()}"
	try:
		cache = frappe.cache() if callable(getattr(frappe, "cache", None)) else frappe.cache
		count = int(cache.incr(key))
		if count == 1:
			cache.expire(key, 60)
	except Exception:
		frappe.logger("vetedge.qa_inspection").exception("QA inspection rate limiter failed")
		frappe.throw("VetEdge QA inspection is temporarily unavailable.", frappe.PermissionError)
	if count > RATE_LIMIT_PER_MINUTE:
		frappe.throw("VetEdge QA inspection rate limit exceeded.", frappe.PermissionError)


def _audit(inspection: str, document_name: str) -> None:
	payload = {
		"inspection": inspection,
		"document_name": document_name,
		"remote_address": _remote_address(),
		"session_user": getattr(getattr(frappe, "session", None), "user", None) or "Guest",
	}
	frappe.logger("vetedge.qa_inspection").info(json.dumps(payload, sort_keys=True))


def _hospitalisation(document_name: str):
	if not document_name or not frappe.db.exists(HOSPITALISATION_DOCTYPE, document_name):
		frappe.throw("Veterinary Hospitalisation was not found.", frappe.DoesNotExistError)
	return frappe.get_doc(HOSPITALISATION_DOCTYPE, document_name)


def _base_context(doc) -> dict:
	return {
		"hospitalisation": doc.name,
		"status": doc.get("status"),
		"service_branch": doc.get("service_branch"),
		"company": doc.get("company"),
		"care_level": doc.get("care_level"),
		"invoice_status": doc.get("invoice_status"),
		"payment_gate_status": doc.get("payment_gate_status"),
	}


def _charge_summary(doc) -> dict:
	rows = []
	for row in doc.get("charge_items") or []:
		rows.append({
			"row_name": row.get("name"),
			"charge_category": row.get("charge_category"),
			"charge_date": row.get("charge_date"),
			"activity_type": row.get("activity_type"),
			"item": row.get("item"),
			"qty": flt(row.get("qty")),
			"uom": row.get("uom"),
			"rate": flt(row.get("rate")),
			"amount": flt(row.get("amount")),
			"billing_status": row.get("billing_status"),
			"sales_invoice": row.get("sales_invoice"),
			"pricing_source": row.get("pricing_source"),
			"source_key": row.get("source_key"),
		})
	return {
		**_base_context(doc),
		"count": len(rows),
		"total_amount": sum(flt(row["amount"]) for row in rows if row.get("billing_status") != "Cancelled"),
		"charges": rows,
	}


def _activity_summary(doc) -> dict:
	rows = []
	for row in doc.get("activities") or []:
		rows.append({
			"row_name": row.get("name"),
			"activity_reference": row.get("activity_reference"),
			"activity_datetime": row.get("activity_datetime"),
			"activity_type": row.get("activity_type"),
			"billable": bool(cint(row.get("billable"))),
			"billing_status": row.get("billing_status"),
			"item": row.get("item"),
			"qty": flt(row.get("qty")),
			"uom": row.get("uom"),
			"stock_affecting": bool(cint(row.get("stock_affecting"))),
			"stock_status": row.get("stock_status"),
			"stock_entry": row.get("stock_entry"),
			"posted_stock_qty": flt(row.get("posted_stock_qty")),
			"linked_doctype": row.get("linked_doctype"),
			"linked_document": row.get("linked_document"),
		})
	return {**_base_context(doc), "count": len(rows), "activities": rows}


def _invoice_names(doc) -> list[str]:
	names = []
	if doc.get("sales_invoice"):
		names.append(doc.get("sales_invoice"))
	for row in doc.get("charge_items") or []:
		if row.get("sales_invoice"):
			names.append(row.get("sales_invoice"))
	return list(dict.fromkeys(name for name in names if name))


def _invoice_summary(doc) -> dict:
	rows = []
	for name in _invoice_names(doc):
		if not frappe.db.exists("Sales Invoice", name):
			rows.append({"name": name, "exists": False})
			continue
		invoice = frappe.db.get_value(
			"Sales Invoice",
			name,
			["name", "docstatus", "status", "posting_date", "company", "grand_total", "outstanding_amount"],
			as_dict=True,
		) or {}
		rows.append({
			"name": invoice.get("name"),
			"exists": True,
			"docstatus": cint(invoice.get("docstatus")),
			"status": invoice.get("status"),
			"posting_date": invoice.get("posting_date"),
			"company": invoice.get("company"),
			"grand_total": flt(invoice.get("grand_total")),
			"outstanding_amount": flt(invoice.get("outstanding_amount")),
		})
	return {**_base_context(doc), "count": len(rows), "invoices": rows}


def _stock_summary(doc) -> dict:
	rows = []
	for activity in doc.get("activities") or []:
		if not cint(activity.get("stock_affecting")) and not activity.get("stock_entry"):
			continue
		row = {
			"activity_reference": activity.get("activity_reference"),
			"activity_type": activity.get("activity_type"),
			"item": activity.get("item"),
			"requested_qty": flt(activity.get("qty")),
			"stock_status": activity.get("stock_status"),
			"stock_entry": activity.get("stock_entry"),
			"posted_stock_qty": flt(activity.get("posted_stock_qty")),
		}
		if activity.get("stock_entry") and frappe.db.exists("Stock Entry", activity.get("stock_entry")):
			entry = frappe.db.get_value(
				"Stock Entry",
				activity.get("stock_entry"),
				["docstatus", "purpose", "posting_date", "posting_time", "company"],
				as_dict=True,
			) or {}
			row["stock_entry_docstatus"] = cint(entry.get("docstatus"))
			row["stock_entry_purpose"] = entry.get("purpose")
			row["stock_entry_posting_date"] = entry.get("posting_date")
			row["stock_entry_posting_time"] = entry.get("posting_time")
			row["stock_entry_company"] = entry.get("company")
		rows.append(row)
	return {**_base_context(doc), "count": len(rows), "stock_postings": rows}


def _payment_gate_summary(doc) -> dict:
	return {
		**_base_context(doc),
		"payment_gate_message": doc.get("payment_gate_message"),
		"discharge_billing_status": doc.get("discharge_billing_status"),
		"discharge_message": doc.get("discharge_message"),
		"invoice_evidence": _invoice_summary(doc)["invoices"],
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def inspect(inspection: str, document_name: str) -> dict:
	_assert_qa_environment()
	token = _assert_service_token()
	_rate_limit(token)
	if inspection not in ALLOWED_INSPECTIONS:
		frappe.throw("Unsupported VetEdge QA inspection type.", frappe.ValidationError)

	doc = _hospitalisation(document_name)
	_audit(inspection, document_name)

	providers = {
		"hospitalisation_charges": _charge_summary,
		"hospitalisation_activities": _activity_summary,
		"related_invoice_summary": _invoice_summary,
		"stock_posting_summary": _stock_summary,
		"payment_gate_evidence": _payment_gate_summary,
	}
	return providers[inspection](doc)
