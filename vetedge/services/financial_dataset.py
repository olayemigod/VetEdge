from __future__ import annotations

from collections import Counter, defaultdict

import frappe
from frappe.utils import cint, cstr, flt

SOURCE_TYPE_TO_INCOME = {
	"Consultation Fee": "Consultation Service Income",
	"Treatment": "Treatment Income",
	"Lab Order": "Laboratory Income",
	"Vaccination": "Vaccination Income",
}
REVENUE_COMPONENT_FIELDS = {
	"Consultation Service Income": "consultation_service_income",
	"Treatment Income": "treatment_income",
	"Laboratory Income": "laboratory_income",
	"Vaccination Income": "vaccination_income",
}


def _income_label(source_type: str | None, fallback: str = "General Income") -> str:
	source_type = cstr(source_type or "").strip()
	if source_type in SOURCE_TYPE_TO_INCOME:
		return SOURCE_TYPE_TO_INCOME[source_type]
	if source_type:
		return source_type if source_type.endswith("Income") else f"{source_type} Income"
	fallback = cstr(fallback or "General").strip() or "General"
	return fallback if fallback.endswith("Income") else f"{fallback} Income"


def _get_consultation_billing_source_map(invoice_names: list[str]) -> dict[str, dict[str, Counter]]:
	result: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
	if not invoice_names or not frappe.db.exists("DocType", "Consultation Billing Source"):
		return result
	rows = frappe.get_all(
		"Consultation Billing Source",
		filters={"sales_invoice": ("in", invoice_names)},
		fields=["sales_invoice", "item_code", "source_type"],
	)
	for row in rows:
		invoice = cstr(row.get("sales_invoice") or "").strip()
		if not invoice:
			continue
		item_code = cstr(row.get("item_code") or "").strip() or "__unlinked__"
		result[invoice][item_code][_income_label(row.get("source_type"))] += 1
	return result


def _get_invoice_item_map(invoice_names: list[str]) -> dict[str, list[dict]]:
	result: dict[str, list[dict]] = defaultdict(list)
	if not invoice_names or not frappe.db.exists("DocType", "Sales Invoice Item"):
		return result
	rows = frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ("in", invoice_names)},
		fields=["parent", "item_code", "net_amount", "amount", "base_net_amount", "base_amount"],
		order_by="parent asc, idx asc",
	)
	for row in rows:
		result[row.get("parent")].append(row)
	return result


def _component_basis(
	invoice_name: str,
	fallback_source: str,
	source_map: dict[str, dict[str, Counter]],
	item_map: dict[str, list[dict]],
) -> dict[str, float]:
	basis: dict[str, float] = defaultdict(float)
	invoice_sources = source_map.get(invoice_name) or {}
	items = item_map.get(invoice_name) or []

	for item in items:
		item_code = cstr(item.get("item_code") or "").strip() or "__unlinked__"
		line_amount = abs(
			flt(item.get("net_amount"))
			or flt(item.get("amount"))
			or flt(item.get("base_net_amount"))
			or flt(item.get("base_amount"))
		)
		if not line_amount:
			continue
		counts = invoice_sources.get(item_code)
		if counts:
			total_count = sum(counts.values()) or 1
			for category, count in counts.items():
				basis[category] += line_amount * (count / total_count)
		else:
			basis[_income_label(None, fallback_source)] += line_amount

	if not basis and invoice_sources:
		for counts in invoice_sources.values():
			for category, count in counts.items():
				basis[category] += float(count)

	if not basis:
		basis[_income_label(None, fallback_source)] = 1.0
	return dict(basis)


def _allocate_revenue_components(
	invoice_name: str,
	fallback_source: str,
	grand_total: float,
	paid_amount: float,
	outstanding_amount: float,
	source_map: dict[str, dict[str, Counter]],
	item_map: dict[str, list[dict]],
) -> list[dict]:
	basis = _component_basis(invoice_name, fallback_source, source_map, item_map)
	total_basis = sum(abs(value) for value in basis.values()) or 1.0
	components = []
	allocated_total = allocated_paid = allocated_outstanding = 0.0
	entries = list(basis.items())
	for index, (category, value) in enumerate(entries):
		last = index == len(entries) - 1
		share = abs(value) / total_basis
		amount = grand_total - allocated_total if last else grand_total * share
		paid = paid_amount - allocated_paid if last else paid_amount * share
		outstanding = outstanding_amount - allocated_outstanding if last else outstanding_amount * share
		components.append(
			{
				"category": category,
				"amount": amount,
				"paid_amount": paid,
				"outstanding_amount": outstanding,
				"share": share,
			}
		)
		allocated_total += amount
		allocated_paid += paid
		allocated_outstanding += outstanding
	return components


def _component_columns(components: list[dict]) -> dict[str, float]:
	columns = {fieldname: 0.0 for fieldname in REVENUE_COMPONENT_FIELDS.values()}
	other_income = 0.0
	for component in components:
		fieldname = REVENUE_COMPONENT_FIELDS.get(component.get("category"))
		if fieldname:
			columns[fieldname] += flt(component.get("amount"))
		else:
			other_income += flt(component.get("amount"))
	columns["other_income"] = other_income
	return columns


def build_financial_dataset(filters=None) -> list[dict]:
	"""Return the permission-compatible Veterinary financial dataset.

	The accounting source remains Sales Invoice. Revenue components are a
	read-only reporting allocation derived from Sales Invoice Item and existing
	Consultation Billing Source rows; no submitted accounting document is changed.
	"""
	filters = frappe._dict(filters or {})

	from vetedge.services.reporting_structure import (
		_build_invoice_context_map,
		_existing_field,
		_get_invoice_payment_branch_map,
		_get_sales_invoice_rows,
		_invoice_status_from_row,
		_resolve_invoice_report_branch,
	)

	invoices = _get_sales_invoice_rows(filters)
	if not invoices:
		return []

	invoice_names = [inv.get("name") for inv in invoices]
	invoice_context = _build_invoice_context_map(invoice_names)
	_get_invoice_payment_branch_map(invoice_names)
	billing_source_map = _get_consultation_billing_source_map(invoice_names)
	invoice_item_map = _get_invoice_item_map(invoice_names)

	consultation_map = {}
	vaccination_map = {}
	lab_map = {}
	boarding_map = {}
	grooming_map = {}
	hospitalisation_map = {}
	billing_session_map = {}

	def populate_link_map(target_doctype, invoice_fields, target_map):
		if not frappe.db.exists("DocType", target_doctype):
			return
		inv_field = _existing_field(target_doctype, invoice_fields)
		if not inv_field:
			return
		branch_field = _existing_field(target_doctype, ["service_branch", "branch"])
		patient_field = _existing_field(target_doctype, ["patient"])
		cost_center_field = _existing_field(target_doctype, ["cost_center"])

		fields_to_get = ["name", inv_field]
		if branch_field:
			fields_to_get.append(branch_field)
		if patient_field:
			fields_to_get.append(patient_field)
		if cost_center_field:
			fields_to_get.append(cost_center_field)

		rows = frappe.get_all(
			target_doctype,
			filters={inv_field: ("in", invoice_names)},
			fields=fields_to_get,
		)
		for row in rows:
			inv_name = row.get(inv_field)
			if inv_name:
				target_map[inv_name] = frappe._dict(
					{
						"name": row.get("name"),
						"sales_invoice": inv_name,
						"patient": row.get(patient_field) if patient_field else None,
						"service_branch": row.get(branch_field) if branch_field else None,
						"branch": row.get(branch_field) if branch_field else None,
						"cost_center": row.get(cost_center_field) if cost_center_field else None,
					}
				)

	populate_link_map("Veterinary Consultation", ["sales_invoice", "linked_invoice", "invoice"], consultation_map)

	if frappe.db.exists("DocType", "Consultation Invoice Reference"):
		child_rows = frappe.get_all(
			"Consultation Invoice Reference",
			filters={"sales_invoice": ("in", invoice_names), "parenttype": "Veterinary Consultation"},
			fields=["parent", "sales_invoice"],
		)
		child_parent_names = [row.parent for row in child_rows if row.parent]
		if child_parent_names:
			branch_field = _existing_field("Veterinary Consultation", ["service_branch", "branch"])
			patient_field = _existing_field("Veterinary Consultation", ["patient"])
			cost_center_field = _existing_field("Veterinary Consultation", ["cost_center"])
			fields_to_get = ["name"]
			for fieldname in (branch_field, patient_field, cost_center_field):
				if fieldname:
					fields_to_get.append(fieldname)
			consultations = frappe.get_all(
				"Veterinary Consultation",
				filters={"name": ("in", child_parent_names)},
				fields=fields_to_get,
			)
			consultation_by_name = {row.name: row for row in consultations}
			for row in child_rows:
				consultation = consultation_by_name.get(row.parent)
				if consultation and row.sales_invoice not in consultation_map:
					consultation_map[row.sales_invoice] = frappe._dict(
						{
							"name": consultation.get("name"),
							"sales_invoice": row.sales_invoice,
							"patient": consultation.get(patient_field) if patient_field else None,
							"service_branch": consultation.get(branch_field) if branch_field else None,
							"branch": consultation.get(branch_field) if branch_field else None,
							"cost_center": consultation.get(cost_center_field) if cost_center_field else None,
						}
					)

	populate_link_map("Veterinary Vaccination Record", ["linked_invoice"], vaccination_map)
	populate_link_map("Veterinary Lab Order", ["linked_invoice", "invoice"], lab_map)
	populate_link_map("Pet Boarding Booking", ["linked_invoice"], boarding_map)
	populate_link_map("Pet Grooming Session", ["linked_invoice"], grooming_map)
	populate_link_map("Veterinary Hospitalisation", ["sales_invoice"], hospitalisation_map)

	if frappe.db.exists("DocType", "Veterinary Billing Session Charge"):
		rows = frappe.get_all(
			"Veterinary Billing Session Charge",
			filters={"invoice": ("in", invoice_names)},
			fields=["parent", "invoice"],
		)
		for row in rows:
			billing_session_map[row.invoice] = row.parent

	dataset = []
	for inv in invoices:
		name = inv.get("name")
		context = invoice_context.get(name, {})
		c_doc = consultation_map.get(name)
		v_doc = vaccination_map.get(name)
		l_doc = lab_map.get(name)
		b_doc = boarding_map.get(name)
		g_doc = grooming_map.get(name)
		h_doc = hospitalisation_map.get(name)
		bs_ref = billing_session_map.get(name)

		patient = context.get("patient")
		if not patient:
			for linked_doc in (c_doc, v_doc, l_doc, b_doc, g_doc, h_doc):
				if linked_doc and linked_doc.get("patient"):
					patient = linked_doc.get("patient")
					break

		resolved_branch = _resolve_invoice_report_branch(inv, context)
		if filters.get("branch") and resolved_branch != cstr(filters.get("branch")).strip():
			continue

		grand_total = flt(inv.get("grand_total"))
		outstanding = flt(inv.get("outstanding_amount"))
		paid_amount = grand_total - outstanding
		if cint(inv.get("docstatus")) == 0:
			outstanding = grand_total
			paid_amount = 0.0

		status_val = inv.get("status") or _invoice_status_from_row(inv)
		service_source = context.get("service_category") or "General"
		components = _allocate_revenue_components(
			name,
			service_source,
			grand_total,
			paid_amount,
			outstanding,
			billing_source_map,
			invoice_item_map,
		)
		component_columns = _component_columns(components)

		dataset.append(
			{
				"sales_invoice": name,
				"posting_date": inv.get("posting_date"),
				"due_date": inv.get("due_date"),
				"company": inv.get("company"),
				"branch": resolved_branch,
				"customer": inv.get("customer"),
				"patient": patient,
				"service_source": service_source,
				"revenue_components": components,
				"revenue_component_labels": [component.get("category") for component in components],
				**component_columns,
				"consultation_reference": c_doc.get("name") if c_doc else None,
				"lab_reference": l_doc.get("name") if l_doc else None,
				"vaccination_reference": v_doc.get("name") if v_doc else None,
				"grooming_reference": g_doc.get("name") if g_doc else None,
				"boarding_reference": b_doc.get("name") if b_doc else None,
				"hospitalisation_reference": h_doc.get("name") if h_doc else None,
				"billing_session_reference": bs_ref,
				"payment_status": status_val,
				"outstanding_amount": outstanding,
				"paid_amount": paid_amount,
				"grand_total": grand_total,
				"docstatus": cint(inv.get("docstatus")),
			}
		)

	return dataset
