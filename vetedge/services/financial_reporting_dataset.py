from __future__ import annotations

from collections import Counter, defaultdict

import frappe
from frappe.utils import cstr, flt

from vetedge.services.financial_dataset import build_financial_dataset as build_legacy_financial_dataset

CONSULTATION_SERVICE_INCOME = "Consultation Service Income"
TREATMENT_INCOME = "Treatment Income"

SOURCE_TYPE_TO_INCOME = {
	"Consultation Fee": CONSULTATION_SERVICE_INCOME,
	"Consultation Service": CONSULTATION_SERVICE_INCOME,
	"Treatment": TREATMENT_INCOME,
	"Lab Order": "Laboratory Income",
	"Laboratory": "Laboratory Income",
	"Vaccination": "Vaccination Income",
	"Grooming": "Grooming Income",
	"Boarding": "Boarding Income",
	"Hospitalisation": "Hospitalisation Income",
	"Dispensary": "Dispensary Income",
	"Registration": "Registration Income",
}
SERVICE_SOURCE_TO_INCOME = {
	"Consultation": TREATMENT_INCOME,
	"Lab": "Laboratory Income",
	"Laboratory": "Laboratory Income",
	"Vaccination": "Vaccination Income",
	"Grooming": "Grooming Income",
	"Boarding": "Boarding Income",
	"Hospitalisation": "Hospitalisation Income",
	"Dispensary": "Dispensary Income",
	"Registration": "Registration Income",
	"General": "Other Income",
}
COMPONENT_FIELDS = {
	CONSULTATION_SERVICE_INCOME: "consultation_service_income",
	TREATMENT_INCOME: "treatment_income",
	"Laboratory Income": "laboratory_income",
	"Vaccination Income": "vaccination_income",
	"Grooming Income": "grooming_income",
	"Boarding Income": "boarding_income",
	"Hospitalisation Income": "hospitalisation_income",
	"Dispensary Income": "dispensary_income",
	"Registration Income": "registration_income",
}


def _configured_consultation_item() -> str:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return ""
	return cstr(frappe.db.get_single_value("Veterinary Settings", "consultation_item") or "").strip()


def _invoice_items(invoice_names: list[str]) -> dict[str, list[dict]]:
	result: dict[str, list[dict]] = defaultdict(list)
	if not invoice_names or not frappe.db.exists("DocType", "Sales Invoice Item"):
		return result
	for row in frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ("in", invoice_names)},
		fields=["parent", "item_code", "net_amount", "amount", "base_net_amount", "base_amount"],
		order_by="parent asc, idx asc",
	):
		result[row.get("parent")].append(row)
	return result


def _explicit_sources(invoice_names: list[str]) -> dict[str, dict[str, Counter]]:
	result: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
	if not invoice_names or not frappe.db.exists("DocType", "Consultation Billing Source"):
		return result
	for row in frappe.get_all(
		"Consultation Billing Source",
		filters={"sales_invoice": ("in", invoice_names)},
		fields=["sales_invoice", "item_code", "source_type"],
	):
		invoice = cstr(row.get("sales_invoice") or "").strip()
		if not invoice:
			continue
		item_code = cstr(row.get("item_code") or "").strip() or "__unlinked__"
		source_type = cstr(row.get("source_type") or "").strip()
		category = SOURCE_TYPE_TO_INCOME.get(source_type)
		if not category and source_type:
			category = source_type if source_type.endswith("Income") else f"{source_type} Income"
		if category:
			result[invoice][item_code][category] += 1
	return result


def _line_amount(item: dict) -> float:
	return abs(
		flt(item.get("net_amount"))
		or flt(item.get("amount"))
		or flt(item.get("base_net_amount"))
		or flt(item.get("base_amount"))
	)


def _linked_service_category(row: dict) -> str:
	if row.get("lab_reference"):
		return "Laboratory Income"
	if row.get("vaccination_reference"):
		return "Vaccination Income"
	if row.get("grooming_reference"):
		return "Grooming Income"
	if row.get("boarding_reference"):
		return "Boarding Income"
	if row.get("hospitalisation_reference"):
		return "Hospitalisation Income"
	if row.get("consultation_reference"):
		return TREATMENT_INCOME
	service_source = cstr(row.get("service_source") or "General").strip() or "General"
	return SERVICE_SOURCE_TO_INCOME.get(
		service_source,
		service_source if service_source.endswith("Income") else f"{service_source} Income",
	)


def _add_explicit_basis(basis: dict[str, float], line_amount: float, counts: Counter | None) -> bool:
	if not counts:
		return False
	total_count = sum(counts.values()) or 1
	for category, count in counts.items():
		basis[category] += line_amount * (count / total_count)
	return True


def _component_basis(
	row: dict,
	items: list[dict],
	sources: dict[str, Counter],
	consultation_item: str,
) -> dict[str, float]:
	basis: dict[str, float] = defaultdict(float)
	is_consultation_invoice = bool(row.get("consultation_reference"))

	for item in items:
		item_code = cstr(item.get("item_code") or "").strip() or "__unlinked__"
		amount = _line_amount(item)
		if not amount:
			continue

		if is_consultation_invoice and consultation_item and item_code == consultation_item:
			# The configured consultation item is authoritative for professional
			# consultation-service income, including older invoices whose source
			# metadata may be missing or ambiguous.
			basis[CONSULTATION_SERVICE_INCOME] += amount
			continue

		if _add_explicit_basis(basis, amount, sources.get(item_code)):
			continue

		if is_consultation_invoice:
			# Every remaining line on a consultation invoice is treatment income
			# unless an explicit source row classified it above as lab, vaccination,
			# grooming, boarding, hospitalisation, or another service.
			basis[TREATMENT_INCOME] += amount
		else:
			basis[_linked_service_category(row)] += amount

	if basis:
		return dict(basis)

	# Older source rows may not contain an item code. Preserve their service
	# classification when an invoice has no usable item amount.
	unlinked = sources.get("__unlinked__")
	if unlinked:
		for category, count in unlinked.items():
			basis[category] += float(count)
		return dict(basis)

	basis[_linked_service_category(row)] = 1.0
	return dict(basis)


def allocate_component_totals(
	basis: dict[str, float],
	grand_total: float,
	paid_amount: float,
	outstanding_amount: float,
) -> list[dict]:
	"""Allocate invoice totals across reporting components without writing accounts."""
	entries = [(category, abs(flt(value))) for category, value in basis.items() if abs(flt(value)) > 0]
	if not entries:
		entries = [("Other Income", 1.0)]
	total_basis = sum(value for _, value in entries) or 1.0
	components = []
	allocated_total = allocated_paid = allocated_outstanding = 0.0

	for index, (category, value) in enumerate(entries):
		last = index == len(entries) - 1
		share = value / total_basis
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
	columns = {fieldname: 0.0 for fieldname in COMPONENT_FIELDS.values()}
	columns["other_income"] = 0.0
	for component in components:
		fieldname = COMPONENT_FIELDS.get(component.get("category"), "other_income")
		columns[fieldname] += flt(component.get("amount"))
	return columns


def classify_financial_row(
	row: dict,
	items: list[dict],
	sources: dict[str, Counter],
	consultation_item: str,
) -> dict:
	basis = _component_basis(row, items, sources, consultation_item)
	components = allocate_component_totals(
		basis,
		flt(row.get("grand_total")),
		flt(row.get("paid_amount")),
		flt(row.get("outstanding_amount")),
	)
	return {
		**row,
		"revenue_components": components,
		"revenue_component_labels": [component.get("category") for component in components],
		**_component_columns(components),
	}


def build_financial_dataset(filters=None) -> list[dict]:
	"""Build component-aware Veterinary financial reporting rows.

	Sales Invoice remains the accounting source of truth. This function reads
	invoice items, Veterinary links and billing-source rows only; it never saves,
	submits or mutates an accounting document.
	"""
	rows = build_legacy_financial_dataset(filters)
	if not rows:
		return []

	invoice_names = [row.get("sales_invoice") for row in rows if row.get("sales_invoice")]
	items_by_invoice = _invoice_items(invoice_names)
	sources_by_invoice = _explicit_sources(invoice_names)
	consultation_item = _configured_consultation_item()

	return [
		classify_financial_row(
			row,
			items_by_invoice.get(row.get("sales_invoice"), []),
			sources_by_invoice.get(row.get("sales_invoice"), {}),
			consultation_item,
		)
		for row in rows
	]
