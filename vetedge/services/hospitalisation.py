from __future__ import annotations

import frappe
from frappe.utils import cint, flt, now, nowdate

from vetedge.services.billing import get_invoice_payment_status
from vetedge.services.payment_gate import (
	FULL_PAYMENT_REQUIRED,
	NO_PAYMENT_GATE,
	PARTIAL_PAYMENT_GATE,
	evaluate_invoice_payment_gate,
)
from vetedge.services.portal_access import require_internal_user
from vetedge.services.registration_billing import get_default_company


SETTINGS_DOCTYPE = "Veterinary Settings"
HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
CHARGE_ITEM_DOCTYPE = "Veterinary Hospitalisation Charge Item"
DISABLED_MESSAGE = "Veterinary Hospitalisation is not enabled for this clinic."
ACTIVE_HOSPITALISATION_STATUSES = {"Draft", "Admitted", "Under Care", "Ready for Discharge"}
DISCHARGE_ALLOWED_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}


def is_hospitalisation_enabled() -> bool:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return False

	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	if not meta.has_field("enable_veterinary_hospitalisation"):
		return False

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	return bool(cint(settings.get("enable_veterinary_hospitalisation")))


def assert_hospitalisation_enabled() -> None:
	if not is_hospitalisation_enabled():
		frappe.throw(DISABLED_MESSAGE, frappe.ValidationError)


def get_hospitalisation_payment_gate() -> str:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return PARTIAL_PAYMENT_GATE

	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	if not meta.has_field("hospitalisation_payment_gate"):
		return PARTIAL_PAYMENT_GATE

	settings = frappe.get_single(SETTINGS_DOCTYPE)
	gate = settings.get("hospitalisation_payment_gate") or PARTIAL_PAYMENT_GATE
	if gate not in {FULL_PAYMENT_REQUIRED, PARTIAL_PAYMENT_GATE, NO_PAYMENT_GATE}:
		return PARTIAL_PAYMENT_GATE
	return gate


def validate_hospitalisation(doc) -> None:
	if doc.is_new():
		assert_hospitalisation_enabled()
	sync_hospitalisation_title(doc)
	normalize_hospitalisation_activities(doc)
	normalize_hospitalisation_charge_items(doc)


def normalize_hospitalisation_activities(doc) -> None:
	for row in doc.get("activities") or []:
		if not row.get("performed_by"):
			row.performed_by = getattr(frappe.session, "user", None)

		if cint(row.get("billable")):
			if row.get("billing_status") in (None, "", "Not Billable"):
				row.billing_status = "Pending Charge"
		else:
			if row.get("billing_status") in (None, "", "Pending Charge"):
				row.billing_status = "Not Billable"

		if cint(row.get("stock_affecting")):
			if row.get("stock_status") in (None, "", "Not Applicable"):
				row.stock_status = "Pending"
		else:
			if row.get("stock_status") in (None, "", "Pending"):
				row.stock_status = "Not Applicable"


def normalize_hospitalisation_charge_items(doc) -> None:
	for row in doc.get("charge_items") or []:
		qty = flt(row.get("qty")) or 1
		rate = flt(row.get("rate"))
		row.qty = qty
		row.amount = qty * rate
		if not row.get("billing_status"):
			row.billing_status = "Pending Invoice"


def sync_hospitalisation_title(doc) -> None:
	parts = [doc.get("patient"), doc.get("status"), doc.get("admission_datetime")]
	doc.hospitalisation_title = " - ".join(str(part) for part in parts if part)


@frappe.whitelist()
def create_hospitalisation_from_consultation(consultation_name: str) -> str:
	require_internal_user()
	assert_hospitalisation_enabled()
	consultation = frappe.get_doc("Veterinary Consultation", consultation_name)

	existing = get_active_hospitalisation_for_consultation(consultation.name)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": HOSPITALISATION_DOCTYPE,
			"patient": consultation.get("patient"),
			"customer": consultation.get("primary_owner"),
			"service_branch": consultation.get("service_branch"),
			"company": consultation.get("company"),
			"linked_consultation": consultation.name,
			"attending_veterinarian": consultation.get("consulting_practitioner"),
			"admission_reason": consultation.get("presenting_complaint") or "Admitted from consultation",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def get_active_hospitalisation_for_consultation(consultation_name: str) -> str | None:
	if not consultation_name or not frappe.db.exists("DocType", HOSPITALISATION_DOCTYPE):
		return None

	rows = frappe.get_all(
		HOSPITALISATION_DOCTYPE,
		filters={
			"linked_consultation": consultation_name,
			"status": ["not in", ["Cancelled", "Discharged"]],
		},
		fields=["name"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0].name if rows else None


@frappe.whitelist()
def create_or_link_hospitalisation_invoice(hospitalisation_name: str) -> str:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)

	if doc.get("sales_invoice") and frappe.db.exists("Sales Invoice", doc.sales_invoice):
		sync_invoice_status(doc)
		return doc.sales_invoice

	invoice = create_hospitalisation_invoice_doc(doc)
	doc.sales_invoice = invoice.name
	doc.invoice_status = get_invoice_payment_status(invoice)
	doc.save(ignore_permissions=True)
	return invoice.name


def create_hospitalisation_invoice_doc(doc, include_default_item: bool = True):
	invoice = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"customer": doc.customer,
			"company": doc.company or get_default_company(),
			"posting_date": nowdate(),
			"due_date": nowdate(),
			"items": build_hospitalisation_invoice_items() if include_default_item else [],
			"remarks": f"VetEdge hospitalisation invoice for {doc.name}",
		}
	)
	apply_hospitalisation_invoice_defaults(doc, invoice)
	invoice.insert(ignore_permissions=True, ignore_mandatory=True)
	return invoice


def build_hospitalisation_invoice_items() -> list[dict]:
	item_code = get_default_hospitalisation_item()
	if not item_code:
		return []
	return [{"item_code": item_code, "qty": 1}]


def get_default_hospitalisation_item() -> str | None:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return None
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	for fieldname in ("default_hospitalisation_item", "hospitalisation_item", "default_hospitalisation_admission_item"):
		if meta.has_field(fieldname):
			value = frappe.get_single(SETTINGS_DOCTYPE).get(fieldname)
			if value and frappe.db.exists("Item", value):
				return value
	return None


def apply_hospitalisation_invoice_defaults(doc, invoice) -> None:
	invoice_meta = frappe.get_meta("Sales Invoice")
	if doc.service_branch and invoice_meta.has_field("branch"):
		invoice.branch = doc.service_branch
	for fieldname in ("hospitalisation", "veterinary_hospitalisation", "vetedge_hospitalisation"):
		if invoice_meta.has_field(fieldname):
			invoice.set(fieldname, doc.name)
			break


def sync_invoice_status(doc) -> None:
	if not doc.get("sales_invoice") or not frappe.db.exists("Sales Invoice", doc.sales_invoice):
		doc.invoice_status = "Not Invoiced"
		doc.save(ignore_permissions=True)
		return
	invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice)
	doc.invoice_status = get_invoice_payment_status(invoice)
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def build_hospitalisation_charge_items(hospitalisation_name: str) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	created = 0
	skipped: list[dict] = []
	existing = 0

	charge_index = get_charge_item_index(doc)
	for activity in doc.get("activities") or []:
		source_activity = get_activity_source_name(activity)
		source_hash = get_activity_source_hash(doc.name, activity)
		if not cint(activity.get("billable")):
			skipped.append({"activity": source_activity, "reason": "not_billable"})
			continue
		if not activity.get("item"):
			skipped.append({"activity": source_activity, "reason": "missing_item"})
			continue
		if activity.get("billing_status") in {"Charged", "Cancelled"}:
			skipped.append({"activity": source_activity, "reason": "activity_not_pending"})
			continue
		if source_hash in charge_index:
			existing += 1
			update_charge_item_from_activity(charge_index[source_hash], activity, source_activity, source_hash)
			continue

		append_charge_item(doc, build_charge_item_row(doc, activity, source_activity, source_hash))
		activity.billing_status = "Pending Charge"
		created += 1

	normalize_hospitalisation_charge_items(doc)
	doc.save(ignore_permissions=True)
	return {"hospitalisation": doc.name, "created": created, "existing": existing, "skipped": skipped}


def get_charge_item_index(doc) -> dict[str, object]:
	index = {}
	for row in doc.get("charge_items") or []:
		key = row.get("source_hash") or row.get("source_activity")
		if key:
			index[key] = row
	return index


def get_activity_source_name(activity) -> str:
	return activity.get("name") or str(activity.get("idx") or "")


def get_activity_source_hash(hospitalisation_name: str, activity) -> str:
	source = get_activity_source_name(activity)
	if source:
		return f"{hospitalisation_name}:{source}"
	return f"{hospitalisation_name}:{activity.get('activity_type')}:{activity.get('item')}:{activity.get('activity_datetime')}:{activity.get('clinical_notes')}"


def build_charge_item_row(doc, activity, source_activity: str, source_hash: str) -> dict:
	qty = flt(activity.get("qty")) or 1
	rate = get_item_rate(activity.get("item"))
	return {
		"source_activity": source_activity,
		"activity_type": activity.get("activity_type"),
		"item": activity.get("item"),
		"item_name": get_item_name(activity.get("item")),
		"description": get_charge_description(activity),
		"qty": qty,
		"uom": activity.get("uom") or get_item_uom(activity.get("item")),
		"rate": rate,
		"amount": qty * rate,
		"billing_status": "Pending Invoice",
		"source_hash": source_hash,
		"notes": activity.get("clinical_notes"),
	}


def update_charge_item_from_activity(row, activity, source_activity: str, source_hash: str) -> None:
	if row.get("billing_status") in {"Invoiced", "Cancelled"}:
		return
	values = build_charge_item_row(None, activity, source_activity, source_hash)
	for fieldname, value in values.items():
		setattr(row, fieldname, value)


def append_charge_item(doc, row: dict) -> None:
	if callable(getattr(doc, "append", None)):
		doc.append("charge_items", row)
		return
	charge_items = doc.get("charge_items") or []
	charge_items.append(frappe._dict(row))
	doc.charge_items = charge_items


def get_item_name(item: str | None) -> str | None:
	if not item:
		return None
	return frappe.db.get_value("Item", item, "item_name") or item


def get_item_uom(item: str | None) -> str | None:
	if not item:
		return None
	return frappe.db.get_value("Item", item, "stock_uom")


def get_item_rate(item: str | None) -> float:
	if not item:
		return 0
	return flt(frappe.db.get_value("Item", item, "standard_rate"))


def get_charge_description(activity) -> str:
	parts = [activity.get("activity_type"), activity.get("clinical_notes")]
	return " - ".join(str(part) for part in parts if part)


@frappe.whitelist()
def sync_hospitalisation_charges_to_invoice(hospitalisation_name: str) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	from vetedge.services.billing_core import is_billing_sessions_enabled

	if is_billing_sessions_enabled():
		return sync_hospitalisation_charges_with_billing_core(hospitalisation_name)

	build_hospitalisation_charge_items(hospitalisation_name)
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	pending = [row for row in doc.get("charge_items") or [] if row.get("billing_status") == "Pending Invoice"]
	if not pending:
		return {
			"hospitalisation": doc.name,
			"invoice": doc.get("sales_invoice"),
			"added_count": 0,
			"skipped_count": 0,
			"created_new_invoice": False,
		}

	invoice, created_new_invoice = get_or_create_charge_invoice(doc)
	added_count = 0
	skipped_count = 0
	existing_sources = get_invoice_charge_sources(invoice)

	for charge in pending:
		if charge.get("source_hash") in existing_sources:
			skipped_count += 1
			mark_charge_invoiced(charge, invoice, None)
			mark_activity_charged(doc, charge)
			continue
		item_row = append_invoice_item_from_charge(invoice, charge)
		mark_charge_invoiced(charge, invoice, item_row)
		mark_activity_charged(doc, charge)
		added_count += 1

	invoice.save(ignore_permissions=True)
	doc.sales_invoice = invoice.name
	doc.invoice_status = get_invoice_payment_status(invoice)
	doc.save(ignore_permissions=True)
	return {
		"hospitalisation": doc.name,
		"invoice": invoice.name,
		"added_count": added_count,
		"skipped_count": skipped_count,
		"created_new_invoice": created_new_invoice,
	}


def sync_hospitalisation_charges_with_billing_core(hospitalisation_name: str) -> dict:
	from vetedge.services.billing_core import BILLING_SESSION_DOCTYPE, sync_source_to_billing_session

	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	previous_status = doc.get("status")
	previous_gate_status = doc.get("payment_gate_status")
	previous_gate_message = doc.get("payment_gate_message")

	result = sync_source_to_billing_session(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	invoice = result.get("invoice")
	if invoice:
		doc.sales_invoice = invoice
		doc.invoice_status = get_invoice_payment_status(frappe.get_doc("Sales Invoice", invoice))

	session_name = result.get("session")
	if session_name and frappe.db.exists(BILLING_SESSION_DOCTYPE, session_name):
		session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
		apply_billing_session_charge_statuses_to_hospitalisation(doc, session)

	doc.status = previous_status
	doc.payment_gate_status = previous_gate_status
	doc.payment_gate_message = previous_gate_message
	doc.save(ignore_permissions=True)
	return {
		"hospitalisation": hospitalisation_name,
		"invoice": invoice,
		"added_count": result.get("added_count", 0),
		"skipped_count": 0,
		"created_new_invoice": bool(result.get("created")),
		"billing_session": session_name,
	}


def apply_billing_session_charge_statuses_to_hospitalisation(doc, session) -> None:
	session_charge_index = {
		get_hospitalisation_charge_source_hash(row): row
		for row in session.get("charges") or []
		if row.get("source_doctype") == HOSPITALISATION_DOCTYPE and row.get("source_name") == doc.name
	}
	for charge in doc.get("charge_items") or []:
		session_charge = session_charge_index.get(charge.get("source_hash"))
		if not session_charge:
			continue
		if session_charge.get("billing_status") in {"Draft Invoiced", "Submitted Invoiced", "Paid"}:
			charge.billing_status = "Invoiced"
			charge.sales_invoice = session_charge.get("invoice")
			charge.sales_invoice_item = session_charge.get("invoice_item_name")
			mark_activity_charged(doc, charge)
		elif session_charge.get("billing_status") == "Cancelled":
			charge.billing_status = "Cancelled"


def get_hospitalisation_charge_source_hash(session_charge) -> str | None:
	charge_key = session_charge.get("charge_key") or ""
	prefix = f"{HOSPITALISATION_DOCTYPE}:{session_charge.get('source_name')}:Hospitalisation:"
	if charge_key.startswith(prefix):
		return charge_key[len(prefix) :]
	return None


def get_or_create_charge_invoice(doc):
	invoice_name = doc.get("sales_invoice")
	if invoice_name and frappe.db.exists("Sales Invoice", invoice_name):
		invoice = frappe.get_doc("Sales Invoice", invoice_name)
		if cint(invoice.docstatus) == 0:
			return invoice, False

	invoice = create_hospitalisation_invoice_doc(doc, include_default_item=False)
	doc.sales_invoice = invoice.name
	doc.invoice_status = get_invoice_payment_status(invoice)
	doc.save(ignore_permissions=True)
	return invoice, True


def get_invoice_charge_sources(invoice) -> set[str]:
	sources = set()
	for row in invoice.get("items") or []:
		for fieldname in ("vetedge_source_hash", "hospitalisation_source_hash", "source_hash"):
			if row.get(fieldname):
				sources.add(row.get(fieldname))
		if row.get("description"):
			marker = "VetEdge hospitalisation charge:"
			if marker in row.description:
				sources.add(row.description.split(marker, 1)[1].strip().split()[0])
	return sources


def append_invoice_item_from_charge(invoice, charge):
	row = {
		"item_code": charge.item,
		"qty": flt(charge.get("qty")) or 1,
		"uom": charge.get("uom"),
		"rate": flt(charge.get("rate")),
		"amount": flt(charge.get("amount")),
		"description": f"{charge.get('description') or charge.item}\nVetEdge hospitalisation charge: {charge.get('source_hash')}",
	}
	meta = frappe.get_meta("Sales Invoice Item") if frappe.db.exists("DocType", "Sales Invoice Item") else None
	if meta:
		for fieldname in ("vetedge_source_hash", "hospitalisation_source_hash", "source_hash"):
			if meta.has_field(fieldname):
				row[fieldname] = charge.get("source_hash")
				break
	if callable(getattr(invoice, "append", None)):
		return invoice.append("items", row)
	items = invoice.get("items") or []
	item_row = frappe._dict(row)
	items.append(item_row)
	invoice.items = items
	return item_row


def mark_charge_invoiced(charge, invoice, item_row) -> None:
	charge.billing_status = "Invoiced"
	charge.sales_invoice = invoice.name
	charge.sales_invoice_item = getattr(item_row, "name", None) or (item_row.get("name") if item_row else charge.get("sales_invoice_item"))


def mark_activity_charged(doc, charge) -> None:
	for activity in doc.get("activities") or []:
		if get_activity_source_hash(doc.name, activity) == charge.get("source_hash"):
			activity.billing_status = "Charged"
			return


@frappe.whitelist()
def get_hospitalisation_charge_summary(hospitalisation_name: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	pending = invoiced = cancelled = 0
	for row in doc.get("charge_items") or []:
		amount = flt(row.get("amount"))
		if row.get("billing_status") == "Invoiced":
			invoiced += amount
		elif row.get("billing_status") == "Cancelled":
			cancelled += amount
		else:
			pending += amount
	return {
		"hospitalisation": doc.name,
		"total_pending": pending,
		"total_invoiced": invoiced,
		"total_cancelled": cancelled,
		"linked_invoice": doc.get("sales_invoice"),
		"invoice_status": doc.get("invoice_status"),
	}


@frappe.whitelist()
def check_hospitalisation_payment_gate(hospitalisation_name: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	result = evaluate_hospitalisation_payment_gate(doc)
	update_payment_gate_fields(doc, result)
	return result


def evaluate_hospitalisation_payment_gate(doc) -> dict:
	gate = get_hospitalisation_payment_gate()
	try:
		from vetedge.services.billing_core import get_payment_gate_status, is_billing_sessions_enabled, resolve_billing_session

		if is_billing_sessions_enabled():
			session = resolve_billing_session(HOSPITALISATION_DOCTYPE, doc.name)
			if session:
				return get_payment_gate_status(session)
	except Exception:
		pass

	invoice_name = doc.get("sales_invoice")
	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		return {
			"gate": gate,
			"can_proceed": False,
			"status": "Blocked",
			"message": "A submitted Sales Invoice is required before hospitalisation care can proceed.",
		}

	invoice = frappe.get_doc("Sales Invoice", invoice_name)
	return evaluate_invoice_payment_gate(invoice, gate, "hospitalisation")


def update_payment_gate_fields(doc, result: dict) -> None:
	doc.payment_gate_status = result.get("status") or ("Allowed" if result.get("can_proceed") else "Blocked")
	doc.payment_gate_message = result.get("message")
	if doc.get("sales_invoice") and frappe.db.exists("Sales Invoice", doc.sales_invoice):
		doc.invoice_status = get_invoice_payment_status(frappe.get_doc("Sales Invoice", doc.sales_invoice))
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def admit_hospitalisation(hospitalisation_name: str) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	create_or_link_hospitalisation_invoice(doc.name)
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	result = evaluate_hospitalisation_payment_gate(doc)
	update_payment_gate_fields(doc, result)

	if not result.get("can_proceed"):
		return result

	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	doc.status = "Admitted" if doc.status == "Draft" else "Under Care"
	doc.admitted_by = frappe.session.user
	doc.save(ignore_permissions=True)
	result["hospitalisation"] = doc.name
	result["status"] = doc.payment_gate_status
	return result


@frappe.whitelist()
def discharge_hospitalisation(hospitalisation_name: str, discharge_summary: str | None = None) -> str:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	if doc.status not in DISCHARGE_ALLOWED_STATUSES:
		frappe.throw("Only admitted hospitalisations can be discharged.", frappe.ValidationError)

	doc.status = "Discharged"
	doc.discharged_by = frappe.session.user
	doc.discharge_datetime = now()
	if discharge_summary is not None:
		doc.discharge_summary = discharge_summary
	doc.save(ignore_permissions=True)
	return doc.name
