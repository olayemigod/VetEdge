from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.utils import cint, flt, now_datetime

from vetedge.services.expiry_control import (
	allocate_item_batches,
	summarize_allocations,
	validate_stock_item_expiry_configuration,
)
from vetedge.services.feature_flags import is_enabled
from vetedge.services.notifications import emit_notification_event
from vetedge.services.portal_access import require_internal_user
from vetedge.services.stock import (
	STOCK_ENTRY_CONSULTATION_FIELD,
	create_material_issue_stock_entry,
	get_branch_dispensary_warehouse,
	get_item_stock_profile,
	validate_stock_availability,
)
from vetedge.services.treatment_items import get_treatment_item_defaults


DISPENSARY_NOT_REQUIRED = "Not Required"
DISPENSARY_PENDING = "Pending Dispensary"
DISPENSARY_CONFIRMED = "Dispensary Confirmed"


@dataclass(frozen=True)
class DispensarySettings:
	enabled: bool


def get_dispensary_settings() -> DispensarySettings:
	return DispensarySettings(enabled=is_enabled("dispensary_flow"))


def get_treatment_type_requires_dispensary(treatment_type: str | None) -> bool:
	if not treatment_type:
		return False

	return bool(
		cint(
			frappe.db.get_value(
				"Veterinary Treatment Type",
				treatment_type,
				"requires_dispensary",
			)
			or 0
		)
	)


def planned_treatment_requires_dispensary(row) -> bool:
	defaults = get_treatment_item_defaults(row.get("item"))
	effective_treatment_type = row.get("treatment_type") or (defaults.treatment_type if defaults else None)

	if get_treatment_type_requires_dispensary(effective_treatment_type):
		return True

	try:
		item = get_item_stock_profile(row.get("item"))
	except Exception:
		return False

	return item.is_stock_item


def get_planned_treatments_requiring_dispensary(doc) -> list:
	return [row for row in (doc.get("planned_treatments") or []) if planned_treatment_requires_dispensary(row)]


def consultation_requires_dispensary(doc) -> bool:
	return bool(get_dispensary_settings().enabled and get_planned_treatments_requiring_dispensary(doc))


def is_dispensary_confirmed(doc) -> bool:
	return bool((doc.get("dispensary_status") or "") == DISPENSARY_CONFIRMED)


def get_consultation_ready_status(doc) -> str:
	if consultation_requires_dispensary(doc) and not is_dispensary_confirmed(doc):
		return "Pending Dispensary"
	return "Ready for Treatment"


def sync_consultation_dispensary_state(doc) -> None:
	if not consultation_requires_dispensary(doc):
		doc.dispensary_status = DISPENSARY_NOT_REQUIRED
		return

	if is_dispensary_confirmed(doc):
		doc.dispensary_status = DISPENSARY_CONFIRMED
		return

	doc.dispensary_status = DISPENSARY_PENDING
	if doc.status == "Ready for Treatment":
		doc.status = "Pending Dispensary"


def validate_consultation_dispensary_requirements(doc) -> None:
	if doc.status not in {"Ready for Treatment", "Completed"}:
		return

	if consultation_requires_dispensary(doc) and not is_dispensary_confirmed(doc):
		frappe.throw(
			"Dispensary confirmation is required before this consultation can move to treatment or completion.",
			frappe.ValidationError,
		)


def build_default_dispensed_items(doc) -> list[dict]:
	rows = []
	for row in get_planned_treatments_requiring_dispensary(doc):
		defaults = get_treatment_item_defaults(row.item)
		profile = get_item_stock_profile(row.item)
		rows.append(
			{
				"planned_treatment_row": row.name,
				"item": row.item,
				"planned_qty": flt(row.qty),
				"dispensed_qty": flt(row.qty),
				"selected_batch": None,
				"batch_allocation_summary": None,
				"uom": row.get("uom") or profile.stock_uom,
				"treatment_type": row.get("treatment_type") or (defaults.treatment_type if defaults else None),
				"stock_item": cint(profile.is_stock_item),
				"notes": row.get("notes"),
			}
		)
	return rows


def normalize_dispensed_items_input(doc, dispensed_items=None) -> list[dict]:
	if dispensed_items in (None, ""):
		return build_default_dispensed_items(doc)

	if isinstance(dispensed_items, str):
		dispensed_items = frappe.parse_json(dispensed_items)

	if not isinstance(dispensed_items, list) or not dispensed_items:
		frappe.throw("Dispensed items must be a non-empty list.", frappe.ValidationError)

	rows_by_name = {row.name: row for row in (doc.get("planned_treatments") or []) if getattr(row, "name", None)}
	normalized = []
	for row in dispensed_items:
		if not isinstance(row, dict):
			row = row.as_dict()
		planned_row = rows_by_name.get(row.get("planned_treatment_row"))
		if not planned_row:
			frappe.throw("Each dispensed row must reference a valid Planned Treatment Item row.", frappe.ValidationError)
		if planned_row.item != row.get("item"):
			frappe.throw("Dispensed item must match its planned treatment item.", frappe.ValidationError)
		qty = flt(row.get("dispensed_qty"))
		if qty <= 0:
			frappe.throw("Dispensed quantity must be greater than zero.", frappe.ValidationError)
		if qty > flt(planned_row.qty) and not row.get("notes"):
			frappe.throw(
				f"Dispensed quantity for {row.get('item')} exceeds the planned quantity. Add notes to justify the variance.",
				frappe.ValidationError,
			)

		profile = get_item_stock_profile(row.get("item"))
		normalized.append(
			{
				"planned_treatment_row": planned_row.name,
				"item": planned_row.item,
				"planned_qty": flt(planned_row.qty),
				"dispensed_qty": qty,
				"selected_batch": row.get("selected_batch"),
				"batch_allocation_summary": row.get("batch_allocation_summary"),
				"uom": row.get("uom") or planned_row.get("uom") or profile.stock_uom,
				"treatment_type": planned_row.get("treatment_type"),
				"stock_item": cint(profile.is_stock_item),
				"notes": row.get("notes") or planned_row.get("notes"),
			}
		)

	return normalized


def is_active_stock_entry(stock_entry_name: str | None) -> bool:
	if not stock_entry_name:
		return False

	docstatus = frappe.db.get_value("Stock Entry", stock_entry_name, "docstatus")
	return docstatus is not None and cint(docstatus) != 2


def validate_dispensary_confirmation_request(doc) -> None:
	settings = get_dispensary_settings()
	if not settings.enabled:
		frappe.throw("Dispensary flow is not enabled.", frappe.ValidationError)
	if doc.status in {"Completed", "Cancelled"}:
		frappe.throw(f"Cannot confirm dispensary for a {doc.status} consultation.", frappe.ValidationError)
	if not consultation_requires_dispensary(doc):
		frappe.throw("This consultation does not require dispensary confirmation.", frappe.ValidationError)
	if is_dispensary_confirmed(doc):
		frappe.throw("Dispensary has already been confirmed for this consultation.", frappe.ValidationError)
	if is_active_stock_entry(doc.get("dispensary_stock_entry")):
		frappe.throw("A submitted dispensary stock issue already exists for this consultation.", frappe.ValidationError)
	if not doc.service_branch:
		frappe.throw("Consultation must have a Service Branch before dispensary confirmation.", frappe.ValidationError)
	if not doc.company:
		frappe.throw("Consultation must have a Company before dispensary confirmation.", frappe.ValidationError)


@frappe.whitelist()
def confirm_dispensary_issue(consultation: str, dispensed_items=None) -> dict:
	require_internal_user()
	doc = frappe.get_doc("Veterinary Consultation", consultation)
	validate_dispensary_confirmation_request(doc)

	dispensed_rows = normalize_dispensed_items_input(doc, dispensed_items)
	warehouse = get_branch_dispensary_warehouse(doc.service_branch, company=doc.company, required=True)
	stock_rows = []
	enriched_rows = []
	for row in dispensed_rows:
		profile = get_item_stock_profile(row.get("item"))
		enriched_row = dict(row)
		enriched_row["source_warehouse"] = warehouse if cint(row.get("stock_item")) else None
		enriched_row["stock_item"] = cint(profile.is_stock_item)
		enriched_row["stock_posted"] = 0
		enriched_row["confirmed_on"] = None
		enriched_row["confirmed_by"] = None
		enriched_row["stock_entry_reference"] = None

		if not cint(profile.is_stock_item):
			enriched_rows.append(enriched_row)
			continue

		try:
			validate_stock_item_expiry_configuration(profile)
		except frappe.ValidationError as exc:
			emit_notification_event(
				"dispensary_expired_stock_blocked",
				doc.doctype,
				doc.name,
				{
					"consultation": doc.name,
					"branch": doc.service_branch,
					"warehouse": warehouse,
					"item": row["item"],
					"error": str(exc),
				},
			)
			raise

		allocations = []
		if profile.has_batch_no:
			try:
				allocations = allocate_item_batches(
					item_code=row["item"],
					warehouse=warehouse,
					qty=flt(row["dispensed_qty"]),
					posting_datetime=now_datetime(),
					manual_batch_no=row.get("selected_batch"),
				)
			except frappe.ValidationError as exc:
				emit_notification_event(
					"dispensary_expired_stock_blocked"
					if row.get("selected_batch")
					else "dispensary_insufficient_non_expired_stock",
					doc.doctype,
					doc.name,
					{
						"consultation": doc.name,
						"branch": doc.service_branch,
						"warehouse": warehouse,
						"item": row["item"],
						"selected_batch": row.get("selected_batch"),
						"error": str(exc),
					},
				)
				raise

		if allocations:
			enriched_row["selected_batch"] = allocations[0].batch_no if len(allocations) == 1 else row.get("selected_batch")
			enriched_row["batch_allocation_summary"] = summarize_allocations(allocations)

		stock_rows.append(
			{
				"item_code": row["item"],
				"qty": row["dispensed_qty"],
				"uom": row.get("uom"),
				"batch_allocations": allocations,
			}
		)
		enriched_rows.append(enriched_row)

	try:
		if stock_rows:
			validate_stock_availability(stock_rows, warehouse)
			stock_entry = create_material_issue_stock_entry(
				consultation_name=doc.name,
				company=doc.company,
				warehouse=warehouse,
				items=stock_rows,
				branch=doc.service_branch,
			)
		else:
			stock_entry = None
	except Exception:
		emit_notification_event(
			"dispensary_stock_issue_failed",
			doc.doctype,
			doc.name,
			{
				"consultation": doc.name,
				"branch": doc.service_branch,
				"warehouse": warehouse,
			},
		)
		raise

	doc.set("dispensed_treatments", [])
	for row in enriched_rows:
		child = doc.append("dispensed_treatments", {})
		for key, value in row.items():
			if callable(getattr(child, "set", None)):
				child.set(key, value)
			else:
				child[key] = value
		child.source_warehouse = row.get("source_warehouse")
		child.stock_posted = cint(row.get("stock_item") and bool(stock_entry))
		child.confirmed_on = now_datetime()
		child.confirmed_by = frappe.session.user
		child.stock_entry_reference = stock_entry

	doc.dispensary_status = DISPENSARY_CONFIRMED
	doc.dispensary_confirmed_by = frappe.session.user
	doc.dispensary_confirmed_on = now_datetime()
	doc.dispensary_stock_entry = stock_entry
	doc.status = "Ready for Treatment"
	doc.save(ignore_permissions=True)

	emit_notification_event(
		"dispensary_confirmation_completed",
		doc.doctype,
		doc.name,
		{
			"consultation": doc.name,
			"stock_entry": stock_entry,
			"branch": doc.service_branch,
			"warehouse": warehouse,
		},
	)
	emit_notification_event(
		"consultation_ready_for_treatment",
		doc.doctype,
		doc.name,
		{
			"consultation": doc.name,
			"stock_entry": stock_entry,
			"payment_status": doc.payment_status,
		},
	)

	return {
		"consultation": doc.name,
		"status": doc.status,
		"dispensary_status": doc.dispensary_status,
		"stock_entry": stock_entry,
	}


@frappe.whitelist()
def get_dispensed_item_preview(consultation: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc("Veterinary Consultation", consultation)

	return {
		"consultation": doc.name,
		"dispensary_status": doc.get("dispensary_status") or DISPENSARY_NOT_REQUIRED,
		"items": build_default_dispensed_items(doc),
	}


def sync_consultation_from_stock_entry(doc, method: str | None = None) -> None:
	if not frappe.get_meta("Stock Entry").has_field(STOCK_ENTRY_CONSULTATION_FIELD):
		return

	consultation_name = doc.get(STOCK_ENTRY_CONSULTATION_FIELD)
	if not consultation_name or cint(doc.docstatus) != 2:
		return

	consultation = frappe.get_doc("Veterinary Consultation", consultation_name)
	if consultation.get("dispensary_stock_entry") != doc.name:
		return

	consultation.dispensary_stock_entry = None
	consultation.dispensary_status = DISPENSARY_PENDING if consultation_requires_dispensary(consultation) else DISPENSARY_NOT_REQUIRED
	if consultation.status == "Ready for Treatment" and consultation.dispensary_status == DISPENSARY_PENDING:
		consultation.status = "Pending Dispensary"
	for row in consultation.get("dispensed_treatments") or []:
		row.stock_posted = 0
	consultation.save(ignore_permissions=True)
