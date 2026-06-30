from __future__ import annotations

import frappe
from frappe.utils import flt


CONSULTATION_DOCTYPE = "Veterinary Consultation"
LAB_ORDER_DOCTYPE = "Veterinary Lab Order"
VACCINATION_RECORD_DOCTYPE = "Veterinary Vaccination Record"
VACCINE_DOCTYPE = "Veterinary Vaccine"
LAB_TEST_DOCTYPE = "Veterinary Lab Test"


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
		if _has_source_row(consultation, "Lab Order", doc.name, source_detail):
			continue

		lab_test = frappe.db.get_value(
			LAB_TEST_DOCTYPE,
			row.get("lab_test_template"),
			["default_rate"],
			as_dict=True,
		) or {}
		_add_plan_row(
			consultation,
			source_type="Lab Order",
			source_doctype=LAB_ORDER_DOCTYPE,
			source_document=doc.name,
			source_detail_name=source_detail,
			item=item,
			description=row.get("lab_test_name") or row.get("lab_test_template"),
			qty=1,
			rate=lab_test.get("default_rate"),
			notes=row.get("notes"),
		)
		changed = True

	if changed:
		_save_consultation(consultation)


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
	item = vaccine.get("default_item")
	if not item:
		return

	consultation = frappe.get_doc(CONSULTATION_DOCTYPE, consultation_name)
	source_detail = doc.get("vaccine") or doc.name
	if _has_source_row(consultation, "Vaccination", doc.name, source_detail):
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
		rate=vaccine.get("default_price"),
		notes=doc.get("notes"),
	)
	_save_consultation(consultation)


def _has_source_row(consultation, source_type: str, source_document: str, source_detail_name: str | None) -> bool:
	for row in consultation.get("planned_treatments") or []:
		if (
			row.get("source_type") == source_type
			and row.get("source_document") == source_document
			and (row.get("source_detail_name") or "") == (source_detail_name or "")
		):
			return True
	return False


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
	consultation.append(
		"planned_treatments",
		{
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
		},
	)


def _save_consultation(consultation) -> None:
	if getattr(consultation, "flags", None) is not None:
		consultation.flags.ignore_permissions = True
	consultation.save(ignore_permissions=True)
