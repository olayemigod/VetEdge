from __future__ import annotations

from typing import Any

import frappe
from frappe import _

from vetedge.services.clinical_workspace import (
	_assert_timestamp,
	_require_clinical_context,
	get_consultation_detail,
)
from vetedge.services.consultation_billing_plan import DEFAULT_CONSULTATION_SOURCE_DETAIL
from vetedge.services.dispensary import (
	DISPENSARY_CONFIRMED,
	DISPENSARY_PENDING,
	build_default_dispensed_items,
	confirm_dispensary_issue,
	get_dispensary_settings,
)
from vetedge.services.permissions import can_access_consultation, can_dispense
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.services.stock import get_branch_dispensary_warehouse

LOCKED_DISPENSARY_COMPLETION_MESSAGE = _(
	"Dispensary confirmation is required before this consultation can be completed. "
	"Review and confirm the dispensary issue first."
)


def enforce_pending_dispensary_completion_invariant(doc, method: str | None = None) -> None:
	"""Prevent every save path from persisting an impossible final workflow state."""
	if doc.get("doctype") != "Veterinary Consultation":
		return
	if (doc.get("status") or "") == "Completed" and (doc.get("dispensary_status") or "") == DISPENSARY_PENDING:
		frappe.throw(LOCKED_DISPENSARY_COMPLETION_MESSAGE, frappe.ValidationError)


def _is_default_consultation_row(row) -> bool:
	return bool(
		row.get("source_type") == "Consultation"
		and row.get("source_detail_name") == DEFAULT_CONSULTATION_SOURCE_DETAIL
	)


def _sort_treatment_order_rows(rows: list[Any]) -> list[Any]:
	"""Newest treatment additions first, with the default consultation fee last."""
	return sorted(
		rows,
		key=lambda row: (
			1 if _is_default_consultation_row(row) else 0,
			-(frappe.utils.get_datetime(row.get("creation") or row.get("modified")).timestamp())
			if row.get("creation") or row.get("modified")
			else 0,
			int(row.get("idx") or 0),
		),
	)


@frappe.whitelist()
def get_treatment_display_order(consultation: str) -> dict:
	_require_clinical_context()
	doc = frappe.get_doc("Veterinary Consultation", consultation)
	doc.check_permission("read")
	can_access_consultation(frappe.session.user, doc.name, raise_exception=True)

	rows = frappe.get_all(
		"Planned Treatment Item",
		filters={"parent": doc.name, "parenttype": doc.doctype},
		fields=[
			"name",
			"idx",
			"creation",
			"modified",
			"source_type",
			"source_detail_name",
		],
		order_by="idx asc",
	)
	ordered = _sort_treatment_order_rows(rows)
	return {
		"consultation": doc.name,
		"order": [row.name for row in ordered],
		"default_consultation_source_detail": DEFAULT_CONSULTATION_SOURCE_DETAIL,
	}


def _dispensary_rows(doc) -> list[dict]:
	stored = doc.get("dispensed_treatments") or []
	rows = stored if stored else build_default_dispensed_items(doc)
	result = []
	for row in rows:
		values = row.as_dict(no_nulls=False) if hasattr(row, "as_dict") else dict(row)
		item = values.get("item")
		result.append(
			{
				"planned_treatment_row": values.get("planned_treatment_row"),
				"item": item,
				"item_name": frappe.db.get_value("Item", item, "item_name") if item else None,
				"planned_qty": values.get("planned_qty"),
				"dispensed_qty": values.get("dispensed_qty"),
				"uom": values.get("uom"),
				"selected_batch": values.get("selected_batch"),
				"batch_allocation_summary": values.get("batch_allocation_summary"),
				"stock_item": values.get("stock_item"),
				"notes": values.get("notes"),
				"stock_posted": values.get("stock_posted"),
				"stock_entry_reference": values.get("stock_entry_reference"),
			}
		)
	return result


@frappe.whitelist()
def get_dispensary_workspace_context(consultation: str) -> dict:
	_require_clinical_context()
	doc = frappe.get_doc("Veterinary Consultation", consultation)
	doc.check_permission("read")
	can_access_consultation(frappe.session.user, doc.name, raise_exception=True)

	can_confirm = bool(can_dispense(frappe.session.user, doc, raise_exception=False))
	warehouse = get_branch_dispensary_warehouse(
		doc.get("service_branch"),
		company=doc.get("company"),
		required=False,
	)
	status = doc.get("dispensary_status") or "Not Required"
	return {
		"consultation": doc.name,
		"modified": doc.modified,
		"patient": doc.get("patient"),
		"patient_label": frappe.db.get_value("Veterinary Patient", doc.get("patient"), "patient_name"),
		"company": doc.get("company"),
		"service_branch": doc.get("service_branch"),
		"warehouse": warehouse,
		"status": status,
		"enabled": bool(get_dispensary_settings().enabled),
		"can_confirm": can_confirm,
		"stock_entry": doc.get("dispensary_stock_entry"),
		"confirmed_by": doc.get("dispensary_confirmed_by"),
		"confirmed_on": doc.get("dispensary_confirmed_on"),
		"items": _dispensary_rows(doc),
		"guidance": (
			_("Review quantities and confirm the dispensary issue.")
			if status == DISPENSARY_PENDING and can_confirm
			else _("A user with dispensary permission must confirm this issue.")
			if status == DISPENSARY_PENDING
			else _("Dispensary issue confirmed.")
			if status == DISPENSARY_CONFIRMED
			else _("This consultation does not currently require dispensary confirmation.")
		),
	}


@frappe.whitelist()
def confirm_workspace_dispensary(
	consultation: str,
	dispensed_items: str | list[dict] | None = None,
	modified: str | None = None,
) -> dict:
	_require_clinical_context()
	doc = frappe.get_doc("Veterinary Consultation", consultation)
	doc.check_permission("read")
	can_access_consultation(frappe.session.user, doc.name, raise_exception=True)
	_assert_timestamp(doc.doctype, doc.name, modified)
	require_vetedge_platform_access(
		action="clinical_workspace_confirm_dispensary",
		reference_doctype=doc.doctype,
		reference_name=doc.name,
	)
	result = confirm_dispensary_issue(doc.name, dispensed_items)
	return {
		**(result or {}),
		"detail": get_consultation_detail(doc.name),
		"context": get_dispensary_workspace_context(doc.name),
	}
