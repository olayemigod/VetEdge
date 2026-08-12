from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services.financial_dataset import build_financial_dataset


SERVICE_CATEGORIES = (
	"Consultation Service",
	"Treatment",
	"Registration",
	"Vaccination",
	"Lab",
	"Grooming",
	"Boarding",
	"Hospitalisation",
	"Dispensary / Pharmacy",
	"General / Other",
)


def _existing_doctype(doctype: str) -> bool:
	return bool(frappe.db.exists("DocType", doctype))


def _single_value(fieldname: str) -> str:
	if not _existing_doctype("Veterinary Settings"):
		return ""
	return cstr(frappe.db.get_single_value("Veterinary Settings", fieldname) or "").strip()


def _pluck_items(doctype: str, fieldname: str) -> set[str]:
	if not _existing_doctype(doctype):
		return set()
	try:
		return {
			cstr(value).strip()
			for value in frappe.get_all(doctype, pluck=fieldname)
			if cstr(value).strip()
		}
	except Exception:
		return set()


def configured_item_categories() -> dict[str, str]:
	"""Return VetEdge master/settings item classifications, strongest rules first."""
	mapping: dict[str, str] = {}

	for item, category in (
		(_single_value("consultation_item"), "Consultation Service"),
		(_single_value("default_registration_item"), "Registration"),
		(_single_value("default_boarding_billing_item"), "Boarding"),
		(_single_value("hospitalisation_admission_fee_item"), "Hospitalisation"),
	):
		if item:
			mapping[item] = category

	for item in _pluck_items("Veterinary Treatment Item", "item"):
		mapping[item] = "Treatment"
	for item in _pluck_items("Veterinary Vaccine", "default_item"):
		mapping[item] = "Vaccination"
	for item in _pluck_items("Veterinary Lab Test", "linked_item"):
		mapping[item] = "Lab"
	for item in _pluck_items("Pet Grooming Service", "default_item"):
		mapping[item] = "Grooming"

	return mapping


def classify_service_line(
	item_code: str | None,
	description: str | None,
	configured: dict[str, str] | None = None,
	fallback_category: str | None = None,
) -> str:
	item = cstr(item_code or "").strip()
	configured = configured or {}
	if item and configured.get(item):
		return configured[item]

	haystack = f"{item} {cstr(description or '')}".lower()
	if "registration" in haystack or "register" in haystack:
		return "Registration"
	if "vaccin" in haystack or "immun" in haystack:
		return "Vaccination"
	if "groom" in haystack:
		return "Grooming"
	if "board" in haystack or "kennel" in haystack:
		return "Boarding"
	if "hospital" in haystack or "admission" in haystack or "ward" in haystack:
		return "Hospitalisation"
	if "lab" in haystack or "diagnostic test" in haystack or "pathology" in haystack:
		return "Lab"
	if any(token in haystack for token in ("treatment", "therapy", "procedure", "wound", "nebul", "fluid therapy")):
		return "Treatment"
	if any(token in haystack for token in ("dispens", "pharmacy", "medicine", "medication", "drug")):
		return "Dispensary / Pharmacy"
	if "consult" in haystack or "examination" in haystack or "exam fee" in haystack:
		return "Consultation Service"

	fallback = cstr(fallback_category or "").strip()
	fallback_map = {
		"Consultation": "Consultation Service",
		"Registration": "Registration",
		"Vaccination": "Vaccination",
		"Lab": "Lab",
		"Grooming": "Grooming",
		"Boarding": "Boarding",
		"Hospitalisation": "Hospitalisation",
		"Dispensary": "Dispensary / Pharmacy",
		"Pharmacy": "Dispensary / Pharmacy",
		"General": "General / Other",
	}
	return fallback_map.get(fallback, fallback if fallback in SERVICE_CATEGORIES else "General / Other")


def _invoice_item_rows(invoice_names: list[str]) -> list[dict]:
	if not invoice_names or not _existing_doctype("Sales Invoice Item"):
		return []
	return frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ("in", invoice_names)},
		fields=[
			"parent",
			"idx",
			"item_code",
			"item_name",
			"description",
			"qty",
			"rate",
			"amount",
			"net_amount",
		],
		order_by="parent asc, idx asc",
	)


def _consultation_practitioners(invoice_rows: list[dict]) -> dict[str, str]:
	consultations = {
		cstr(row.get("consultation_reference")).strip()
		for row in invoice_rows
		if cstr(row.get("consultation_reference")).strip()
	}
	if not consultations or not _existing_doctype("Veterinary Consultation"):
		return {}
	meta = frappe.get_meta("Veterinary Consultation")
	practitioner_field = next(
		(
			fieldname
			for fieldname in ("consulting_practitioner_name", "consulting_practitioner", "practitioner")
			if meta.get_field(fieldname)
		),
		None,
	)
	if not practitioner_field:
		return {}
	return {
		cstr(row.get("name")): cstr(row.get(practitioner_field) or "").strip()
		for row in frappe.get_all(
			"Veterinary Consultation",
			filters={"name": ("in", sorted(consultations))},
			fields=["name", practitioner_field],
		)
	}


def _allocate_invoice(
	invoice: dict,
	items: list[dict],
	configured: dict[str, str],
	practitioner: str = "",
) -> list[dict]:
	grand_total = flt(invoice.get("grand_total"))
	paid_total = flt(invoice.get("paid_amount"))
	outstanding_total = flt(invoice.get("outstanding_amount"))
	basis = [max(flt(row.get("net_amount") or row.get("amount")), 0) for row in items]
	basis_total = sum(basis)

	if not items or basis_total <= 0:
		return [
			{
				"invoice": invoice.get("sales_invoice"),
				"posting_date": invoice.get("posting_date"),
				"customer": invoice.get("customer"),
				"branch": invoice.get("branch"),
				"practitioner": practitioner,
				"service_category": classify_service_line(
					"",
					"",
					configured,
					invoice.get("service_source"),
				),
				"item_code": "",
				"item_name": _("Invoice total"),
				"qty": 1,
				"rate": grand_total,
				"line_net_amount": grand_total,
				"revenue_amount": grand_total,
				"paid_amount": paid_total,
				"outstanding_amount": outstanding_total,
			}
		]

	allocated = []
	for index, item in enumerate(items):
		share = basis[index] / basis_total if basis_total else 0
		allocated.append(
			{
				"invoice": invoice.get("sales_invoice"),
				"posting_date": invoice.get("posting_date"),
				"customer": invoice.get("customer"),
				"branch": invoice.get("branch"),
				"practitioner": practitioner,
				"service_category": classify_service_line(
					item.get("item_code"),
					item.get("description") or item.get("item_name"),
					configured,
					invoice.get("service_source"),
				),
				"item_code": item.get("item_code"),
				"item_name": item.get("item_name") or item.get("item_code"),
				"qty": flt(item.get("qty")),
				"rate": flt(item.get("rate")),
				"line_net_amount": basis[index],
				"revenue_amount": grand_total * share,
				"paid_amount": paid_total * share,
				"outstanding_amount": outstanding_total * share,
			}
		)
	return allocated


def build_service_revenue_rows(filters=None, dataset: list[dict] | None = None) -> list[dict]:
	"""Build a line-level, total-preserving service revenue dataset for submitted invoices."""
	filters = frappe._dict(filters or {})
	base_filters = frappe._dict(
		{
			key: value
			for key, value in filters.items()
			if key not in {"service_category", "item", "practitioner"}
		}
	)
	invoice_rows = list(dataset if dataset is not None else build_financial_dataset(base_filters))
	invoice_rows = [row for row in invoice_rows if cint(row.get("docstatus")) == 1]
	invoice_map = {
		cstr(row.get("sales_invoice")): row
		for row in invoice_rows
		if cstr(row.get("sales_invoice")).strip()
	}
	if not invoice_map:
		return []

	configured = configured_item_categories()
	items_by_invoice: dict[str, list[dict]] = defaultdict(list)
	for item in _invoice_item_rows(sorted(invoice_map)):
		items_by_invoice[cstr(item.get("parent"))].append(item)

	practitioners_by_consultation = _consultation_practitioners(invoice_rows)
	rows: list[dict] = []
	for invoice_name, invoice in invoice_map.items():
		practitioner = practitioners_by_consultation.get(cstr(invoice.get("consultation_reference")), "")
		rows.extend(
			_allocate_invoice(
				invoice,
				items_by_invoice.get(invoice_name, []),
				configured,
				practitioner,
			)
		)

	service_category = cstr(filters.get("service_category") or "").strip()
	item_filter = cstr(filters.get("item") or "").strip()
	practitioner_filter = cstr(filters.get("practitioner") or "").strip()
	if service_category:
		rows = [row for row in rows if cstr(row.get("service_category")) == service_category]
	if item_filter:
		rows = [row for row in rows if cstr(row.get("item_code")) == item_filter]
	if practitioner_filter:
		rows = [row for row in rows if cstr(row.get("practitioner")) == practitioner_filter]
	return rows


def summarize_service_revenue(rows: list[dict], key_field: str = "service_category") -> list[dict]:
	grouped: dict[str, dict] = {}
	for row in rows:
		key = cstr(row.get(key_field) or _("Unassigned")).strip() or _("Unassigned")
		bucket = grouped.setdefault(
			key,
			{
				key_field: key,
				"revenue_amount": 0.0,
				"paid_amount": 0.0,
				"outstanding_amount": 0.0,
				"line_count": 0,
			},
		)
		bucket["revenue_amount"] += flt(row.get("revenue_amount"))
		bucket["paid_amount"] += flt(row.get("paid_amount"))
		bucket["outstanding_amount"] += flt(row.get("outstanding_amount"))
		bucket["line_count"] += 1
	return sorted(grouped.values(), key=lambda row: (-flt(row.get("revenue_amount")), cstr(row.get(key_field))))


def service_revenue_report(filters=None):
	rows = build_service_revenue_rows(filters)
	columns = [
		{"fieldname": "invoice", "label": _("Sales Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch", "width": 150},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 170},
		{"fieldname": "practitioner", "label": _("Practitioner"), "fieldtype": "Data", "width": 170},
		{"fieldname": "service_category", "label": _("Service Category"), "fieldtype": "Data", "width": 170},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 150},
		{"fieldname": "item_name", "label": _("Item Name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "qty", "label": _("Qty"), "fieldtype": "Float", "width": 90},
		{"fieldname": "revenue_amount", "label": _("Revenue"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "paid_amount", "label": _("Paid"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "outstanding_amount", "label": _("Outstanding"), "fieldtype": "Currency", "width": 120},
	]
	composition = summarize_service_revenue(rows)
	chart = {
		"data": {
			"labels": [row["service_category"] for row in composition],
			"datasets": [{"name": _("Revenue"), "values": [row["revenue_amount"] for row in composition]}],
		},
		"type": "donut",
		"title": _("Revenue by Service Line"),
	}
	summary = [
		{"label": _("Revenue"), "value": sum(flt(row.get("revenue_amount")) for row in rows), "indicator": "Green"},
		{"label": _("Paid"), "value": sum(flt(row.get("paid_amount")) for row in rows), "indicator": "Blue"},
		{"label": _("Outstanding"), "value": sum(flt(row.get("outstanding_amount")) for row in rows), "indicator": "Orange"},
	]
	return columns, rows, None, chart, summary
