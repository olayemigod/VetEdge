from __future__ import annotations

import frappe
from frappe.utils import cint, flt, now_datetime

from vetedge.services.notifications import emit_notification_event
from vetedge.services.permissions import (
	can_access_branch_data,
	can_access_consultation,
	can_access_lab_order,
	can_enter_lab_results,
	can_request_lab_tests,
	can_review_lab_results,
	get_current_user,
)
from vetedge.services.portal_access import require_internal_user


LAB_TEST_DOCTYPE = "Veterinary Lab Test"
LAB_ORDER_DOCTYPE = "Veterinary Lab Order"
LAB_ORDER_ITEM_DOCTYPE = "Veterinary Lab Order Item"

LAB_ORDER_STATUSES = {
	"Draft",
	"Requested",
	"Sample Collected",
	"In Progress",
	"Result Entered",
	"Reviewed",
	"Cancelled",
}

VALID_LAB_ORDER_STATUS_TRANSITIONS = {
	"Draft": {"Requested", "Cancelled"},
	"Requested": {"Sample Collected", "In Progress", "Cancelled"},
	"Sample Collected": {"In Progress", "Cancelled"},
	"In Progress": {"Result Entered", "Cancelled"},
	"Result Entered": {"Reviewed", "Cancelled"},
	"Reviewed": set(),
	"Cancelled": set(),
}

LAB_RESULT_FIELDS = ("result_value", "result_text", "remarks")
LAB_REVIEW_FINAL_STATUSES = {"Reviewed", "Cancelled"}
LAB_RESULT_ENTRY_STATUSES = {"Sample Collected", "In Progress", "Result Entered"}


def validate_lab_test(doc) -> None:
	from vetedge.services.billing import validate_sales_item

	if not doc.test_name:
		frappe.throw("Test Name is required for Veterinary Lab Test.", frappe.ValidationError)

	doc.test_name = str(doc.test_name).strip()
	if doc.test_code:
		doc.test_code = str(doc.test_code).strip().upper()

	if doc.default_rate is not None and flt(doc.default_rate) < 0:
		frappe.throw("Default Rate cannot be negative.", frappe.ValidationError)

	if doc.linked_item:
		validate_sales_item(doc.linked_item, "Linked Item", allow_stock=False)


def validate_lab_order(doc) -> None:
	previous = doc.get_doc_before_save() if getattr(doc, "get_doc_before_save", None) else None

	validate_lab_order_status(doc, previous)
	resolve_lab_order_context(doc)
	validate_lab_order_consultation_link(doc)
	validate_lab_order_branch_access(doc)
	validate_lab_order_request_permissions(doc, previous)
	validate_lab_order_result_permissions(doc, previous)
	validate_lab_order_items(doc)
	validate_lab_order_status_requirements(doc)
	sync_lab_order_review_metadata(doc)


def validate_lab_order_status(doc, previous=None) -> None:
	if not doc.status:
		doc.status = "Draft"

	if doc.status not in LAB_ORDER_STATUSES:
		frappe.throw(f"Invalid lab order status: {doc.status}", frappe.ValidationError)

	if previous and previous.status in LAB_REVIEW_FINAL_STATUSES and previous.status != doc.status:
		frappe.throw(
			f"Lab order status cannot be changed after it is {previous.status}.",
			frappe.ValidationError,
		)

	if previous and previous.status != doc.status:
		allowed = VALID_LAB_ORDER_STATUS_TRANSITIONS.get(previous.status, set())
		if doc.status not in allowed:
			frappe.throw(
				f"Lab order status cannot move from {previous.status} to {doc.status}.",
				frappe.ValidationError,
			)


def resolve_lab_order_context(doc) -> None:
	if not doc.patient:
		frappe.throw("Patient is required for Veterinary Lab Order.", frappe.ValidationError)

	patient = frappe.db.get_value(
		"Veterinary Patient",
		doc.patient,
		["primary_owner", "default_branch"],
		as_dict=True,
	)
	if not patient:
		frappe.throw("Veterinary Lab Order must reference a valid Veterinary Patient.", frappe.ValidationError)

	if doc.consultation:
		consultation = frappe.db.get_value(
			"Veterinary Consultation",
			doc.consultation,
			["patient", "primary_owner", "service_branch"],
			as_dict=True,
		)
		if not consultation:
			frappe.throw("Consultation must be a valid Veterinary Consultation.", frappe.ValidationError)
		if consultation.patient != doc.patient:
			frappe.throw("Consultation must belong to the selected patient.", frappe.ValidationError)
		if not doc.primary_owner and consultation.primary_owner:
			doc.primary_owner = consultation.primary_owner
		if not doc.service_branch and consultation.service_branch:
			doc.service_branch = consultation.service_branch

	if not doc.primary_owner:
		doc.primary_owner = patient.primary_owner

	if not doc.primary_owner:
		frappe.throw("Patient must have a linked owner before a lab order can be created.", frappe.ValidationError)

	if not doc.service_branch:
		doc.service_branch = patient.default_branch

	if not doc.service_branch:
		frappe.throw("Service Branch is required for Veterinary Lab Order.", frappe.ValidationError)

	if not doc.requested_on:
		doc.requested_on = now_datetime()

	if not doc.requested_by:
		doc.requested_by = get_current_user()

	set_lab_order_title(doc)


def validate_lab_order_consultation_link(doc) -> None:
	if not doc.consultation:
		return

	can_access_consultation(get_current_user(), doc.consultation, raise_exception=True)


def validate_lab_order_branch_access(doc) -> None:
	can_access_branch_data(get_current_user(), doc.service_branch, raise_exception=True)


def validate_lab_order_request_permissions(doc, previous=None) -> None:
	user = get_current_user()
	if not user or user == "Guest":
		return

	if previous is None:
		can_request_lab_tests(user, doc, raise_exception=True)
		return

	if _lab_request_structure_changed(doc, previous):
		can_request_lab_tests(user, doc, raise_exception=True)


def validate_lab_order_result_permissions(doc, previous=None) -> None:
	user = get_current_user()
	if not user or user == "Guest":
		return

	if previous and _has_reviewed_result_edit(doc, previous):
		frappe.throw(
			"Reviewed lab results are read-only and cannot be edited.",
			frappe.ValidationError,
		)

	if previous is None:
		if doc.status in LAB_RESULT_ENTRY_STATUSES:
			can_enter_lab_results(user, doc, raise_exception=True)
		elif doc.status == "Reviewed":
			can_review_lab_results(user, doc, raise_exception=True)
		return

	if doc.status != previous.status:
		if doc.status in LAB_RESULT_ENTRY_STATUSES:
			can_enter_lab_results(user, doc, raise_exception=True)
		elif doc.status == "Reviewed":
			can_review_lab_results(user, doc, raise_exception=True)
		elif doc.status == "Cancelled" and (previous.status not in LAB_REVIEW_FINAL_STATUSES):
			if not (
				can_enter_lab_results(user, doc, raise_exception=False)
				or can_review_lab_results(user, doc, raise_exception=False)
			):
				frappe.throw("Only authorized lab or doctor/admin roles can cancel this lab order.", frappe.PermissionError)

	if previous and _lab_result_content_changed(doc, previous):
		can_enter_lab_results(user, doc, raise_exception=True)


def validate_lab_order_items(doc) -> None:
	from vetedge.services.billing import validate_sales_item

	rows = doc.get("lab_tests") or []
	if not rows and doc.status != "Cancelled":
		frappe.throw("At least one lab test is required on a lab order.", frappe.ValidationError)

	seen_templates: set[str] = set()
	current_user = get_current_user()
	for row in rows:
		if not row.lab_test_template:
			frappe.throw("Each lab order row must reference a Veterinary Lab Test.", frappe.ValidationError)
		if row.lab_test_template in seen_templates:
			frappe.throw(
				f"Lab Test {row.lab_test_template} appears more than once in this order.",
				frappe.ValidationError,
			)
		seen_templates.add(row.lab_test_template)

		lab_test = frappe.db.get_value(
			LAB_TEST_DOCTYPE,
			row.lab_test_template,
			["test_name", "sample_type", "linked_item", "default_rate", "is_active"],
			as_dict=True,
		)
		if not lab_test:
			frappe.throw(f"Lab Test {row.lab_test_template} is not valid.", frappe.ValidationError)
		if not cint(lab_test.is_active):
			frappe.throw(f"Lab Test {row.lab_test_template} is inactive.", frappe.ValidationError)

		row.lab_test_name = lab_test.test_name
		if not row.sample_type and lab_test.sample_type:
			row.sample_type = lab_test.sample_type
		if not row.billing_item and lab_test.linked_item:
			row.billing_item = lab_test.linked_item
		if row.billing_item:
			validate_sales_item(row.billing_item, "Lab Billing Item", allow_stock=False)

		has_result = any(row.get(fieldname) not in (None, "") for fieldname in LAB_RESULT_FIELDS)
		if has_result:
			if not row.entered_by:
				row.entered_by = current_user
			if not row.entered_on:
				row.entered_on = now_datetime()
			if row.result_status in (None, "", "Pending"):
				row.result_status = "Entered"
			if row.status not in {"Reviewed", "Cancelled"}:
				row.status = "Result Entered"
		else:
			if not row.result_status:
				row.result_status = "Pending"
			if doc.status in {"Requested", "Sample Collected", "In Progress"}:
				row.status = doc.status
			elif not row.status:
				row.status = "Requested"

		if doc.status == "Reviewed" and row.status != "Cancelled":
			row.status = "Reviewed"
			row.result_status = "Reviewed"


def validate_lab_order_status_requirements(doc) -> None:
	if doc.status not in {"Result Entered", "Reviewed"}:
		return

	for row in doc.get("lab_tests") or []:
		if row.status == "Cancelled":
			continue
		if not any(row.get(fieldname) not in (None, "") for fieldname in LAB_RESULT_FIELDS):
			frappe.throw(
				f"Enter a result value or result text for {row.lab_test_template} before marking this lab order as {doc.status}.",
				frappe.ValidationError,
			)


def sync_lab_order_review_metadata(doc) -> None:
	if doc.status != "Reviewed":
		return

	reviewer = get_current_user()
	can_review_lab_results(reviewer, doc, raise_exception=True)
	if not doc.doctor_reviewed_by:
		doc.doctor_reviewed_by = reviewer
	if not doc.doctor_reviewed_on:
		doc.doctor_reviewed_on = now_datetime()


def handle_lab_order_after_insert(doc) -> None:
	emit_notification_event(
		"lab_order_created",
		doc.doctype,
		doc.name,
		{
			"patient": doc.patient,
			"primary_owner": doc.primary_owner,
			"consultation": doc.consultation,
			"branch": doc.service_branch,
			"requested_by": doc.requested_by,
			"status": doc.status,
		},
	)


def handle_lab_order_on_update(doc) -> None:
	previous = doc.get_doc_before_save()
	if not previous or previous.status == doc.status:
		return

	payload = {
		"patient": doc.patient,
		"primary_owner": doc.primary_owner,
		"consultation": doc.consultation,
		"branch": doc.service_branch,
		"status": doc.status,
	}
	if doc.status == "Sample Collected":
		emit_notification_event("lab_sample_collected", doc.doctype, doc.name, payload)
	elif doc.status == "Result Entered":
		emit_notification_event("lab_result_entered", doc.doctype, doc.name, payload)
		emit_notification_event("lab_result_ready_for_review", doc.doctype, doc.name, payload)


@frappe.whitelist()
def transition_lab_order_status(lab_order: str, status: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc(LAB_ORDER_DOCTYPE, lab_order)
	can_access_lab_order(get_current_user(), lab_order, raise_exception=True)
	previous_status = doc.status
	doc.status = status
	doc.save()
	return {
		"name": doc.name,
		"previous_status": previous_status,
		"status": doc.status,
	}


@frappe.whitelist()
def create_lab_order_from_consultation(
	consultation: str,
	lab_tests: list[dict] | str | None = None,
	sample_notes: str | None = None,
) -> dict:
	require_internal_user()
	can_access_consultation(get_current_user(), consultation, raise_exception=True)
	consultation_doc = frappe.get_doc("Veterinary Consultation", consultation)
	from vetedge.services.consultation_flow import validate_consultation_allows_new_clinical_entries

	validate_consultation_allows_new_clinical_entries(consultation_doc, entry_type="lab orders")
	can_request_lab_tests(get_current_user(), consultation_doc, raise_exception=True)
	from vetedge.services.platform_access import require_vetedge_platform_access
	require_vetedge_platform_access(
		action="create_lab_order_from_consultation",
		reference_doctype="Veterinary Consultation",
		reference_name=consultation
	)

	rows = normalize_lab_tests_payload(lab_tests)
	if not rows:
		frappe.throw("Select at least one lab test before creating a lab order.", frappe.ValidationError)

	doc = frappe.get_doc(
		{
			"doctype": LAB_ORDER_DOCTYPE,
			"patient": consultation_doc.patient,
			"primary_owner": consultation_doc.primary_owner,
			"consultation": consultation_doc.name,
			"service_branch": consultation_doc.service_branch,
			"requested_by": get_current_user(),
			"requested_on": now_datetime(),
			"status": "Requested",
			"sample_notes": sample_notes,
			"lab_tests": rows,
		}
	)
	doc.insert(ignore_permissions=True)

	return {
		"name": doc.name,
		"status": doc.status,
	}


def normalize_lab_tests_payload(lab_tests: list[dict] | str | None) -> list[dict]:
	if not lab_tests:
		return []

	if isinstance(lab_tests, str):
		lab_tests = frappe.parse_json(lab_tests)
	if isinstance(lab_tests, dict):
		lab_tests = [lab_tests]

	rows = []
	for row in lab_tests or []:
		if isinstance(row, str):
			rows.append({"lab_test_template": row})
			continue
		if not row:
			continue
		row = frappe._dict(row)
		rows.append(
			{
				"lab_test_template": row.get("lab_test_template") or row.get("name") or row.get("test"),
				"notes": row.get("notes"),
				"sample_type": row.get("sample_type"),
			}
		)
	return [row for row in rows if row.get("lab_test_template")]


def set_lab_order_title(doc) -> None:
	patient_name = frappe.db.get_value("Veterinary Patient", doc.patient, "patient_name") if doc.patient else None
	if hasattr(patient_name, "get"):
		patient_name = patient_name.get("patient_name") or patient_name.get("name")
	requested_date = str(doc.requested_on or now_datetime())[:10]
	parts = [part for part in [patient_name, requested_date, "Lab Order", doc.service_branch] if part]
	doc.lab_order_title = " - ".join(parts)


@frappe.whitelist()
def get_active_lab_tests_for_picker() -> list[dict]:
	require_internal_user()
	return frappe.get_all(
		LAB_TEST_DOCTYPE,
		filters={"is_active": 1},
		fields=["name", "test_name", "sample_type", "linked_item", "default_rate"],
		order_by="test_name asc",
	)


@frappe.whitelist()
def get_consultation_lab_orders_for_popup(consultation: str) -> list[dict]:
	require_internal_user()
	can_access_consultation(get_current_user(), consultation, raise_exception=True)

	return frappe.get_all(
		LAB_ORDER_DOCTYPE,
		filters={"consultation": consultation},
		fields=["name", "lab_order_title", "status", "requested_on", "requested_by"],
		order_by="requested_on desc, modified desc",
	)


@frappe.whitelist()
def get_lab_order_popup_summary(lab_order: str) -> dict:
	require_internal_user()
	can_access_lab_order(get_current_user(), lab_order, raise_exception=True)
	order = frappe.get_doc(LAB_ORDER_DOCTYPE, lab_order)
	invoice = None
	if order.get("linked_invoice") and frappe.db.exists("Sales Invoice", order.linked_invoice):
		invoice_doc = frappe.get_doc("Sales Invoice", order.linked_invoice)
		invoice = {
			"name": invoice_doc.name,
			"status": invoice_doc.get("status"),
			"docstatus": cint(invoice_doc.docstatus),
			"grand_total": flt(invoice_doc.get("grand_total")),
			"paid_amount": flt(invoice_doc.get("paid_amount")),
			"outstanding_amount": flt(invoice_doc.get("outstanding_amount")),
			"currency": invoice_doc.get("currency"),
		}

	return {
		"name": order.name,
		"title": order.get("lab_order_title"),
		"patient": order.get("patient"),
		"primary_owner": order.get("primary_owner"),
		"consultation": order.get("consultation"),
		"requested_by": order.get("requested_by"),
		"requested_on": order.get("requested_on"),
		"service_branch": order.get("service_branch"),
		"status": order.get("status"),
		"sample_notes": order.get("sample_notes"),
		"invoice": invoice,
		"lab_tests": [
			{
				"lab_test_template": row.get("lab_test_template"),
				"test_name": frappe.db.get_value(LAB_TEST_DOCTYPE, row.get("lab_test_template"), "test_name")
				or row.get("lab_test_template"),
				"billing_item": row.get("billing_item"),
				"status": row.get("status"),
				"result_status": row.get("result_status"),
				"notes": row.get("notes"),
			}
			for row in order.get("lab_tests") or []
		],
	}


@frappe.whitelist()
def create_lab_test_from_dialog(values: dict | str | None = None) -> dict:
	require_internal_user()
	user = get_current_user()
	if not (can_request_lab_tests(user, raise_exception=False) or can_enter_lab_results(user, raise_exception=False)):
		frappe.throw("You are not allowed to create lab tests.", frappe.PermissionError)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	values = frappe._dict(values or {})

	doc = frappe.get_doc(
		{
			"doctype": LAB_TEST_DOCTYPE,
			"test_name": values.get("test_name"),
			"test_code": values.get("test_code"),
			"description": values.get("description"),
			"sample_type": values.get("sample_type"),
			"linked_item": values.get("linked_item"),
			"default_rate": values.get("default_rate"),
			"is_active": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "test_name": doc.test_name}


@frappe.whitelist()
def create_standalone_lab_order(
	patient: str,
	lab_tests: list[dict] | str | None = None,
	service_branch: str | None = None,
	sample_notes: str | None = None,
) -> dict:
	require_internal_user()
	can_request_lab_tests(get_current_user(), raise_exception=True)
	from vetedge.services.platform_access import require_vetedge_platform_access
	require_vetedge_platform_access(
		action="create_standalone_lab_order",
		reference_doctype="Veterinary Patient",
		reference_name=patient
	)
	rows = normalize_lab_tests_payload(lab_tests)
	if not rows:
		frappe.throw("Select at least one lab test before creating a lab order.", frappe.ValidationError)

	patient_context = frappe.db.get_value(
		"Veterinary Patient",
		patient,
		["primary_owner", "default_branch"],
		as_dict=True,
	)
	if not patient_context:
		frappe.throw("Patient must be a valid Veterinary Patient.", frappe.ValidationError)

	doc = frappe.get_doc(
		{
			"doctype": LAB_ORDER_DOCTYPE,
			"patient": patient,
			"primary_owner": patient_context.primary_owner,
			"service_branch": service_branch or patient_context.default_branch,
			"requested_by": get_current_user(),
			"requested_on": now_datetime(),
			"status": "Requested",
			"sample_notes": sample_notes,
			"lab_tests": rows,
		}
	)
	doc.insert(ignore_permissions=True)
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def create_lab_order_invoice(lab_order: str) -> dict:
	from vetedge.services.registration_billing import get_billing_cost_center

	require_internal_user()
	can_access_lab_order(get_current_user(), lab_order, raise_exception=True)
	from vetedge.services.platform_access import require_vetedge_platform_access
	require_vetedge_platform_access(
		action="create_lab_order_invoice",
		reference_doctype="Veterinary Lab Order",
		reference_name=lab_order
	)

	order = frappe.get_doc(LAB_ORDER_DOCTYPE, lab_order)
	if is_persisted_lab_order_for_billing_core(order) and use_billing_core_for_lab_order():
		from vetedge.services.billing_core import sync_source_to_billing_session

		result = sync_source_to_billing_session(LAB_ORDER_DOCTYPE, order.name)
		invoice_name = result.get("invoice")
		if invoice_name:
			frappe.db.set_value(LAB_ORDER_DOCTYPE, order.name, "linked_invoice", invoice_name, update_modified=False)
		return {"lab_order": order.name, "invoice": invoice_name, "created": bool(result.get("created")), "billing_session": result.get("session")}

	if order.consultation:
		frappe.throw(
			"Consultation-linked lab orders are billed through the consultation invoice flow.",
			frappe.ValidationError,
		)
	if not order.primary_owner:
		frappe.throw("Lab order must have a primary owner before billing.", frappe.ValidationError)
	if not order.service_branch:
		frappe.throw("Lab order must have a service branch before billing.", frappe.ValidationError)

	cost_center = get_billing_cost_center(order.service_branch, required=True)
	items = build_lab_order_invoice_items(order, cost_center)
	if not items:
		frappe.throw("No billable lab items were found on this lab order.", frappe.ValidationError)

	if order.linked_invoice and frappe.db.exists("Sales Invoice", order.linked_invoice):
		linked_invoice = frappe.get_doc("Sales Invoice", order.linked_invoice)
		if cint(linked_invoice.docstatus) == 0:
			update_draft_lab_order_invoice(linked_invoice, order, items, cost_center)
			return {"lab_order": order.name, "invoice": linked_invoice.name, "created": False}
		if cint(linked_invoice.docstatus) == 1:
			return {"lab_order": order.name, "invoice": linked_invoice.name, "created": False, "submitted": True}

	invoice = create_lab_order_sales_invoice(order, items, cost_center)
	frappe.db.set_value(LAB_ORDER_DOCTYPE, order.name, "linked_invoice", invoice.name, update_modified=False)
	emit_notification_event(
		"invoice_created",
		"Sales Invoice",
		invoice.name,
		{
			"customer": order.primary_owner,
			"branch": order.service_branch,
			"lab_order": order.name,
			"amount": invoice.grand_total,
		},
	)
	return {"lab_order": order.name, "invoice": invoice.name, "created": True}


def build_lab_order_invoice_items(order, cost_center: str) -> list[dict]:
	from vetedge.services.billing import build_invoice_item

	items = []
	for row in order.get("lab_tests") or []:
		if not row.billing_item:
			continue
		default_rate = frappe.db.get_value(LAB_TEST_DOCTYPE, row.lab_test_template, "default_rate")
		items.append(build_invoice_item(row.billing_item, 1, None, default_rate, cost_center))
	return items


def is_persisted_lab_order_for_billing_core(order) -> bool:
	db = getattr(frappe, "db", None)
	if not db or not hasattr(db, "exists"):
		return False
	return bool(order.get("name") and db.exists(LAB_ORDER_DOCTYPE, order.name))


def use_billing_core_for_lab_order() -> bool:
	try:
		from vetedge.services.billing_core import is_billing_sessions_enabled

		return is_billing_sessions_enabled()
	except Exception:
		return False


def create_lab_order_sales_invoice(order, items: list[dict], cost_center: str):
	from vetedge.services.registration_billing import get_default_company

	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": order.primary_owner,
			"company": get_default_company(),
			"posting_date": frappe.utils.nowdate(),
			"due_date": frappe.utils.nowdate(),
			"items": items,
			"remarks": f"Lab billing for {order.name}",
		}
	)
	if order.service_branch and frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = order.service_branch
	if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = cost_center
	invoice.insert(ignore_permissions=True)
	return invoice


def update_draft_lab_order_invoice(invoice, order, items: list[dict], cost_center: str) -> None:
	if invoice.customer and invoice.customer != order.primary_owner:
		frappe.throw("Linked Invoice customer does not match the lab order owner.", frappe.ValidationError)
	invoice.customer = order.primary_owner
	invoice.posting_date = frappe.utils.nowdate()
	invoice.due_date = frappe.utils.nowdate()
	invoice.remarks = f"Lab billing for {order.name}"
	if order.service_branch and frappe.get_meta("Sales Invoice").has_field("branch"):
		invoice.branch = order.service_branch
	if cost_center and frappe.get_meta("Sales Invoice").has_field("cost_center"):
		invoice.cost_center = cost_center
	invoice.set("items", [])
	for item in items:
		invoice.append("items", item)
	invoice.save(ignore_permissions=True)


def get_consultation_lab_billing_items(consultation_doc, cost_center: str, invoice_name: str | None = None) -> tuple[list[dict], list[dict]]:
	from vetedge.services.billing import build_invoice_item

	if not consultation_doc.name:
		return [], []
	if not _doctype_is_available(LAB_ORDER_DOCTYPE):
		return [], []

	lab_orders = frappe.get_all(
		LAB_ORDER_DOCTYPE,
		filters={
			"consultation": consultation_doc.name,
			"status": ["!=", "Cancelled"],
		},
		fields=["name", "linked_invoice"],
	)
	order_names = [row.name for row in lab_orders if not row.linked_invoice or row.linked_invoice == invoice_name]
	if not order_names:
		return [], []

	lab_rows = frappe.get_all(
		LAB_ORDER_ITEM_DOCTYPE,
		filters={
			"parent": ["in", order_names],
		},
		fields=["parent", "lab_test_template", "billing_item"],
		order_by="idx asc",
	)

	items = []
	sources = []
	for row in lab_rows:
		if not row.billing_item:
			continue
		default_rate = frappe.db.get_value(LAB_TEST_DOCTYPE, row.lab_test_template, "default_rate")
		items.append(build_invoice_item(row.billing_item, 1, None, default_rate, cost_center))
		sources.append(
			{
				"source_type": "Lab Order",
				"source_name": row.parent,
				"sales_invoice": invoice_name,
				"item_code": row.billing_item,
			}
		)
	return items, sources


def mark_consultation_lab_orders_invoiced(consultation: str, invoice: str) -> None:
	if not consultation or not invoice:
		return
	if not _doctype_is_available(LAB_ORDER_DOCTYPE):
		return

	for row in frappe.get_all(
		LAB_ORDER_DOCTYPE,
		filters={
			"consultation": consultation,
			"status": ["!=", "Cancelled"],
		},
		fields=["name", "linked_invoice"],
	):
		if row.linked_invoice:
			continue
		frappe.db.set_value(LAB_ORDER_DOCTYPE, row.name, "linked_invoice", invoice, update_modified=False)


def get_lab_history(patient: str, limit: int, from_date: str | None = None, to_date: str | None = None) -> list[dict]:
	from vetedge.services.medical_history import get_date_filters

	if not _doctype_is_available(LAB_ORDER_DOCTYPE):
		return []

	orders = frappe.get_list(
		LAB_ORDER_DOCTYPE,
		filters=get_date_filters("requested_on", from_date, to_date, {"patient": patient}),
		fields=[
			"name",
			"consultation",
			"requested_on",
			"requested_by",
			"service_branch",
			"status",
			"doctor_reviewed_by",
			"doctor_reviewed_on",
		],
		order_by="requested_on desc, modified desc",
		limit=limit,
	)
	if not orders:
		return []

	items_by_order = _get_lab_order_items_summary([row.name for row in orders])
	return [
		{
			"type": "lab",
			"name": row.name,
			"timestamp": row.requested_on,
			"consultation": row.consultation,
			"requested_by": row.requested_by,
			"service_branch": row.service_branch,
			"status": row.status,
			"doctor_reviewed_by": row.doctor_reviewed_by,
			"doctor_reviewed_on": row.doctor_reviewed_on,
			"tests": items_by_order.get(row.name, {}).get("tests", []),
			"tests_summary": items_by_order.get(row.name, {}).get("tests_summary", ""),
			"results_summary": items_by_order.get(row.name, {}).get("results_summary", ""),
		}
		for row in orders
	]


def _get_lab_order_items_summary(order_names: list[str]) -> dict[str, dict]:
	if not order_names:
		return {}

	rows = frappe.get_all(
		LAB_ORDER_ITEM_DOCTYPE,
		filters={"parent": ["in", order_names]},
		fields=["parent", "lab_test_name", "lab_test_template", "result_value", "result_text"],
		order_by="idx asc",
	)
	result: dict[str, dict] = {}
	for row in rows:
		entry = result.setdefault(row.parent, {"tests": [], "tests_summary": "", "results_summary": ""})
		test_name = row.lab_test_name or row.lab_test_template
		if test_name:
			entry["tests"].append(test_name)
		result_value = row.result_text or row.result_value
		if result_value not in (None, ""):
			entry.setdefault("result_rows", []).append(f"{test_name}: {result_value}")

	for entry in result.values():
		entry["tests_summary"] = ", ".join(entry.get("tests", []))
		entry["results_summary"] = "; ".join(entry.get("result_rows", []))
		entry.pop("result_rows", None)

	return result


def _lab_request_structure_changed(doc, previous) -> bool:
	if any(
		(doc.get(fieldname) or None) != (previous.get(fieldname) or None)
		for fieldname in ("patient", "primary_owner", "consultation", "service_branch")
	):
		return True

	return _serialize_request_rows(doc) != _serialize_request_rows(previous)


def _serialize_request_rows(doc) -> list[tuple]:
	return [
		(
			row.get("lab_test_template"),
			row.get("notes"),
			row.get("sample_type"),
			row.get("billing_item"),
		)
		for row in doc.get("lab_tests") or []
	]


def _lab_result_content_changed(doc, previous) -> bool:
	current_rows = {row.name or f"idx-{idx}": row for idx, row in enumerate(doc.get("lab_tests") or [], start=1)}
	previous_rows = {row.name or f"idx-{idx}": row for idx, row in enumerate(previous.get("lab_tests") or [], start=1)}

	for key, row in current_rows.items():
		previous_row = previous_rows.get(key)
		if not previous_row:
			continue
		for fieldname in LAB_RESULT_FIELDS + ("status", "result_status"):
			if (row.get(fieldname) or None) != (previous_row.get(fieldname) or None):
				return True
	return False


def _has_reviewed_result_edit(doc, previous) -> bool:
	current_rows = {row.name or f"idx-{idx}": row for idx, row in enumerate(doc.get("lab_tests") or [], start=1)}
	previous_rows = {row.name or f"idx-{idx}": row for idx, row in enumerate(previous.get("lab_tests") or [], start=1)}

	for key, previous_row in previous_rows.items():
		if (previous_row.get("result_status") or None) != "Reviewed":
			continue
		current_row = current_rows.get(key)
		if not current_row:
			return True
		for fieldname in LAB_RESULT_FIELDS + ("status", "result_status", "entered_by", "entered_on"):
			if (current_row.get(fieldname) or None) != (previous_row.get(fieldname) or None):
				return True
	return False


def _doctype_is_available(doctype: str) -> bool:
	try:
		return bool(frappe.db.exists("DocType", doctype))
	except RuntimeError:
		return False
