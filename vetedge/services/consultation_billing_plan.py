from __future__ import annotations

import frappe
from frappe.utils import flt


CONSULTATION_DOCTYPE = "Veterinary Consultation"
LAB_ORDER_DOCTYPE = "Veterinary Lab Order"
VACCINATION_RECORD_DOCTYPE = "Veterinary Vaccination Record"
VACCINE_DOCTYPE = "Veterinary Vaccine"
LAB_TEST_DOCTYPE = "Veterinary Lab Test"
DEFAULT_CONSULTATION_SOURCE_DETAIL = "Default Consultation Fee"


def ensure_default_consultation_item_to_plan(doc) -> bool:
	from vetedge.services.billing import get_consultation_billing_settings, should_auto_add_default_consultation_item
	from vetedge.services.treatment_items import get_planned_treatment_item_billing_defaults

	if not doc or doc.doctype != CONSULTATION_DOCTYPE:
		return False
	settings = get_consultation_billing_settings()
	if not should_auto_add_default_consultation_item(settings):
		return False

	item = settings.consultation_item
	existing_row = _get_source_row(doc, "Consultation", doc.name, DEFAULT_CONSULTATION_SOURCE_DETAIL)
	defaults = get_planned_treatment_item_billing_defaults(
		item,
		company=doc.get("company"),
		customer=doc.get("primary_owner"),
		branch=doc.get("service_branch"),
	)
	rate = defaults.rate if defaults else None
	if existing_row:
		return _update_default_consultation_plan_row(existing_row, doc, item, rate)

	_add_plan_row(
		doc,
		source_type="Consultation",
		source_doctype=CONSULTATION_DOCTYPE,
		source_document=doc.name,
		source_detail_name=DEFAULT_CONSULTATION_SOURCE_DETAIL,
		item=item,
		description="Consultation Fee",
		qty=1,
		rate=rate,
		notes=None,
	)
	return True


def validate_default_consultation_plan_row_edit(doc) -> None:
	from vetedge.services.billing import can_edit_default_consultation_billing_item, get_consultation_billing_settings, should_auto_add_default_consultation_item

	settings = get_consultation_billing_settings()
	if not should_auto_add_default_consultation_item(settings) or can_edit_default_consultation_billing_item(settings):
		return
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None
	if not previous:
		return
	old_row = _get_source_row(previous, "Consultation", previous.name, DEFAULT_CONSULTATION_SOURCE_DETAIL)
	new_row = _get_source_row(doc, "Consultation", doc.name, DEFAULT_CONSULTATION_SOURCE_DETAIL)
	if not old_row or not new_row:
		return
	protected_fields = ("item", "qty", "rate")
	for fieldname in protected_fields:
		old_value = flt(old_row.get(fieldname)) if fieldname in {"qty", "rate", "amount"} else old_row.get(fieldname)
		new_value = flt(new_row.get(fieldname)) if fieldname in {"qty", "rate", "amount"} else new_row.get(fieldname)
		if old_value != new_value:
			frappe.throw("Default consultation billing item editing is disabled in Veterinary Settings.", frappe.ValidationError)


def _update_default_consultation_plan_row(plan_row, doc, item: str, rate: float | None) -> bool:
	if not _can_update_plan_row_from_source(plan_row):
		return False
	if plan_row.get("item") != item:
		return False
	qty = flt(plan_row.get("qty")) or 1
	new_values = {
		"source_doctype": CONSULTATION_DOCTYPE,
		"source_document": doc.name,
		"description": plan_row.get("description") or "Consultation Fee",
		"qty": qty,
		"amount": qty * flt(plan_row.get("rate") if plan_row.get("rate") not in (None, "") else rate),
	}
	if plan_row.get("rate") in (None, ""):
		new_values["rate"] = flt(rate)
	changed = False
	for fieldname, value in new_values.items():
		if plan_row.get(fieldname) != value:
			_set_child_value(plan_row, fieldname, value)
			changed = True
	return changed


def sync_lab_order_to_consultation_plan(doc) -> None:
	consultation_name = doc.get("consultation")
	if not consultation_name or doc.get("status") == "Cancelled":
		return

	consultation = frappe.get_doc(CONSULTATION_DOCTYPE, consultation_name)
	changed = False
	for row in doc.get("lab_tests") or []:
		item = row.get("billing_item")
		if not item:
			continue
		source_detail = row.get("name") or row.get("lab_test_template")
		existing_row = _get_source_row(consultation, "Lab Order", doc.name, source_detail)
		rate = _get_lab_order_row_rate(row)
		if existing_row:
			if _update_plan_row_from_lab_order(existing_row, row, item, rate):
				changed = True
			continue

		_add_plan_row(
			consultation,
			source_type="Lab Order",
			source_doctype=LAB_ORDER_DOCTYPE,
			source_document=doc.name,
			source_detail_name=source_detail,
			item=item,
			description=row.get("lab_test_name") or row.get("lab_test_template"),
			qty=1,
			rate=rate,
			notes=row.get("notes"),
		)
		changed = True

	if changed:
		_save_consultation(consultation)
		_sync_active_consultation_billing_session(consultation)


def sync_vaccination_to_consultation_plan(doc) -> None:
	consultation_name = doc.get("linked_consultation")
	if not consultation_name or doc.get("status") == "Cancelled":
		return

	vaccine = frappe.db.get_value(
		VACCINE_DOCTYPE,
		doc.get("vaccine"),
		["vaccine_name", "default_item", "default_price"],
		as_dict=True,
	) or {}
	item = doc.get("billing_item") or vaccine.get("default_item")
	if not item:
		return

	consultation = frappe.get_doc(CONSULTATION_DOCTYPE, consultation_name)
	source_detail = doc.get("vaccine") or doc.name
	rate = doc.get("rate") if doc.get("rate") not in (None, "") else vaccine.get("default_price")
	existing_row = _get_source_row(consultation, "Vaccination", doc.name, source_detail)
	if existing_row:
		if _update_plan_row_from_vaccination(existing_row, doc, item, vaccine.get("vaccine_name"), rate):
			_save_consultation(consultation)
		return

	_add_plan_row(
		consultation,
		source_type="Vaccination",
		source_doctype=VACCINATION_RECORD_DOCTYPE,
		source_document=doc.name,
		source_detail_name=source_detail,
		item=item,
		description=vaccine.get("vaccine_name") or doc.get("vaccine"),
		qty=1,
		rate=rate,
		notes=doc.get("notes"),
	)
	_save_consultation(consultation)


def _has_source_row(consultation, source_type: str, source_document: str, source_detail_name: str | None) -> bool:
	return _get_source_row(consultation, source_type, source_document, source_detail_name) is not None


def _get_source_row(consultation, source_type: str, source_document: str, source_detail_name: str | None):
	for row in consultation.get("planned_treatments") or []:
		if (
			row.get("source_type") == source_type
			and row.get("source_document") == source_document
			and (row.get("source_detail_name") or "") == (source_detail_name or "")
		):
			return row
	return None


def _get_lab_order_row_rate(row) -> float | None:
	if row.get("rate") not in (None, ""):
		return flt(row.get("rate"))
	lab_test = frappe.db.get_value(
		LAB_TEST_DOCTYPE,
		row.get("lab_test_template"),
		["default_rate"],
		as_dict=True,
	) or {}
	return lab_test.get("default_rate")


def _update_plan_row_from_lab_order(plan_row, lab_row, item: str, rate: float | None) -> bool:
	if not _can_update_plan_row_from_source(plan_row):
		return False
	qty = flt(plan_row.get("qty")) or 1
	new_values = {
		"item": item,
		"description": lab_row.get("lab_test_name") or lab_row.get("lab_test_template"),
		"qty": qty,
		"rate": flt(rate),
		"amount": qty * flt(rate),
		"notes": lab_row.get("notes"),
	}
	changed = False
	for fieldname, value in new_values.items():
		if plan_row.get(fieldname) != value:
			_set_child_value(plan_row, fieldname, value)
			changed = True
	return changed


def _update_plan_row_from_vaccination(plan_row, doc, item: str, vaccine_name: str | None, rate: float | None) -> bool:
	if not _can_update_plan_row_from_source(plan_row):
		return False
	qty = flt(plan_row.get("qty")) or 1
	new_values = {
		"item": item,
		"description": vaccine_name or doc.get("vaccine"),
		"qty": qty,
		"rate": flt(rate),
		"amount": qty * flt(rate),
		"notes": doc.get("notes"),
	}
	changed = False
	for fieldname, value in new_values.items():
		if plan_row.get(fieldname) != value:
			_set_child_value(plan_row, fieldname, value)
			changed = True
	return changed


def _set_child_value(row, fieldname: str, value) -> None:
	setter = getattr(row, "set", None)
	if callable(setter):
		setter(fieldname, value)
		return
	if hasattr(row, "__setitem__"):
		row[fieldname] = value
		return
	setattr(row, fieldname, value)


def _can_update_plan_row_from_source(row) -> bool:
	if row.get("billing_status") in {"Submitted Invoiced", "Paid", "Cancelled", "Skipped"}:
		return False
	if row.get("payment_status") in {"Paid", "Partly Paid", "Cancelled"}:
		return False
	return True


def _add_plan_row(
	consultation,
	*,
	source_type: str,
	source_doctype: str,
	source_document: str,
	source_detail_name: str | None,
	item: str,
	description: str | None,
	qty: float,
	rate: float | None,
	notes: str | None = None,
) -> None:
	qty = flt(qty) or 1
	rate = flt(rate)
	row = {
		"item": item,
		"description": description,
		"qty": qty,
		"rate": rate,
		"amount": qty * rate,
		"source_type": source_type,
		"source_doctype": source_doctype,
		"source_document": source_document,
		"source_detail_name": source_detail_name,
		"billing_status": "Pending",
		"payment_status": "Not Billed",
		"notes": notes,
	}
	append = getattr(consultation, "append", None)
	if callable(append):
		append("planned_treatments", row)
	else:
		consultation.setdefault("planned_treatments", []).append(frappe._dict(row))


def _save_consultation(consultation) -> None:
	if getattr(consultation, "flags", None) is not None:
		consultation.flags.ignore_permissions = True
	flags = getattr(frappe, "flags", None)
	previous_core = getattr(flags, "vetedge_billing_core_syncing", False) if flags else False
	previous_modal = getattr(flags, "vetedge_billing_modal_syncing", False) if flags else False
	previous_lock_bypass = getattr(flags, "ignore_consultation_treatment_lock_for_billing_sync", False) if flags else False
	if flags is not None:
		flags.vetedge_billing_core_syncing = True
		flags.ignore_consultation_treatment_lock_for_billing_sync = True
	try:
		consultation.save(ignore_permissions=True)
	finally:
		if flags is not None:
			flags.vetedge_billing_core_syncing = previous_core
			flags.vetedge_billing_modal_syncing = previous_modal
			flags.ignore_consultation_treatment_lock_for_billing_sync = previous_lock_bypass


def _sync_active_consultation_billing_session(consultation) -> None:
	"""Push newly-linked Lab charges into an already-open Consultation billing cycle.

	Creating a Lab Order should not create a billing session on its own. If billing has
	already started for the Consultation, however, the new plan row must be reconciled
	into that session immediately. Billing Core remains authoritative for draft updates,
	new-draft creation after a submitted invoice, and submitted-invoice immutability.
	"""
	flags = getattr(frappe, "flags", None)
	if getattr(flags, "vetedge_billing_core_syncing", False):
		return
	from vetedge.services.billing_core import (
		is_billing_sessions_enabled,
		resolve_billing_session,
		sync_source_to_billing_session,
	)

	if not is_billing_sessions_enabled():
		return
	session = resolve_billing_session(CONSULTATION_DOCTYPE, consultation.name)
	if not session:
		return
	sync_source_to_billing_session(CONSULTATION_DOCTYPE, consultation.name)
