from __future__ import annotations

import uuid

import frappe
from frappe.utils import cint, flt, formatdate, get_datetime, getdate, now

from vetedge.services.billing import get_invoice_payment_status
from vetedge.services.payment_gate import (
	FULL_PAYMENT_REQUIRED,
	NO_PAYMENT_GATE,
	PARTIAL_PAYMENT_GATE,
	evaluate_invoice_payment_gate,
)
from vetedge.services.portal_access import require_internal_user


SETTINGS_DOCTYPE = "Veterinary Settings"
HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
CHARGE_ITEM_DOCTYPE = "Veterinary Hospitalisation Charge Item"
DISABLED_MESSAGE = "Veterinary Hospitalisation is not enabled for this clinic."
ACTIVE_HOSPITALISATION_STATUSES = {"Draft", "Admitted", "Under Care", "Ready for Discharge"}
DISCHARGE_ALLOWED_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}
VALID_HOSPITALISATION_INVOICE_STATUSES = {"Not Invoiced", "Draft", "Unpaid", "Partly Paid", "Paid", "Overdue", "Cancelled"}


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
		if not row.get("activity_reference"):
			row.activity_reference = generate_hospitalisation_activity_reference()
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
		if row.get("item") and rate <= 0 and row.get("billing_status") != "Invoiced":
			pricing = resolve_hospitalisation_charge_pricing(doc, row.get("item"), row.get("uom"))
			rate = flt(pricing.get("rate"))
			if rate > 0:
				row.rate = rate
				if hasattr(row, "pricing_source"):
					row.pricing_source = pricing.get("pricing_source")
		row.qty = qty
		row.amount = qty * rate
		if not row.get("billing_status"):
			row.billing_status = "Pending Invoice"


def generate_hospitalisation_activity_reference() -> str:
	try:
		return frappe.generate_hash(length=12)
	except Exception:
		return uuid.uuid4().hex[:12]


def sync_hospitalisation_title(doc) -> None:
	patient_title = get_hospitalisation_patient_title(doc)
	parts = [patient_title or "Hospitalisation"]
	admission_date = get_hospitalisation_admission_date_title(doc)
	veterinarian_title = get_hospitalisation_veterinarian_title(doc)
	if admission_date:
		parts.append(admission_date)
	if veterinarian_title:
		parts.append(veterinarian_title)
	if patient_title:
		parts.append("Hospitalisation")
	doc.hospitalisation_title = " - ".join(parts)


def get_hospitalisation_patient_title(doc) -> str | None:
	patient = doc.get("patient")
	if not patient:
		return None
	try:
		return frappe.db.get_value("Veterinary Patient", patient, "patient_name") or patient
	except Exception:
		return patient


def get_hospitalisation_admission_date_title(doc) -> str | None:
	admission_datetime = doc.get("admission_datetime")
	if not admission_datetime:
		return None
	try:
		return formatdate(getdate(admission_datetime))
	except Exception:
		return str(admission_datetime)


def get_hospitalisation_veterinarian_title(doc) -> str | None:
	veterinarian = doc.get("attending_veterinarian") or doc.get("admitted_by")
	if not veterinarian:
		return None
	try:
		return frappe.db.get_value("User", veterinarian, "full_name") or veterinarian
	except Exception:
		return veterinarian


@frappe.whitelist()
def get_hospitalisation_patient_context(patient: str) -> dict:
	require_internal_user()
	if not patient:
		return {}
	patient_doc = frappe.get_doc("Veterinary Patient", patient)
	return {
		"patient": patient_doc.name,
		"patient_name": patient_doc.get("patient_name") or patient_doc.name,
		"customer": patient_doc.get("primary_owner"),
		"primary_owner": patient_doc.get("primary_owner"),
		"service_branch": patient_doc.get("default_branch"),
		"default_branch": patient_doc.get("default_branch"),
		"species": patient_doc.get("species"),
		"breed": patient_doc.get("breed"),
		"sex": patient_doc.get("sex"),
		"age": patient_doc.get("approximate_age") or patient_doc.get("age"),
		"approximate_age": patient_doc.get("approximate_age"),
		"date_of_birth": patient_doc.get("date_of_birth"),
		"owner_contact": patient_doc.get("owner_contact") or patient_doc.get("primary_contact"),
	}


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
	doc.insert()
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
	result = sync_hospitalisation_charges_with_billing_core(hospitalisation_name)
	return result.get("invoice")


def create_hospitalisation_invoice_doc(doc, include_default_item: bool = True):
	frappe.throw(
		"Hospitalisation invoices are managed by VetEdge Billing Core. Use create_or_link_hospitalisation_invoice instead.",
		frappe.ValidationError,
	)


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


def get_hospitalisation_invoice_status(invoice=None, status: str | None = None) -> str:
	if invoice is not None:
		if cint(invoice.get("docstatus")) == 0:
			return "Draft"
		if cint(invoice.get("docstatus")) == 2:
			return "Cancelled"
		status = get_invoice_payment_status(invoice)
	status = status or "Not Invoiced"
	status_map = {
		"Draft Invoice Pending": "Draft",
		"Pending Invoice": "Not Invoiced",
		"Partially Paid": "Partly Paid",
	}
	status = status_map.get(status, status)
	return status if status in VALID_HOSPITALISATION_INVOICE_STATUSES else "Not Invoiced"


def sync_invoice_status(doc) -> None:
	if not doc.get("sales_invoice") or not frappe.db.exists("Sales Invoice", doc.sales_invoice):
		doc.invoice_status = "Not Invoiced"
		doc.save()
		return
	invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice)
	doc.invoice_status = get_hospitalisation_invoice_status(invoice)
	doc.save()


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
		existing_row = next((charge_index.get(key) for key in get_activity_charge_lookup_keys(doc.name, activity) if charge_index.get(key)), None)
		if existing_row:
			existing += 1
			update_charge_item_from_activity(existing_row, activity, source_activity, source_hash, doc)
			continue

		append_charge_item(doc, build_charge_item_row(doc, activity, source_activity, source_hash))
		activity.billing_status = "Pending Charge"
		created += 1

	normalize_hospitalisation_charge_items(doc)
	doc.save()
	return {"hospitalisation": doc.name, "created": created, "existing": existing, "skipped": skipped}


def get_charge_item_index(doc) -> dict[str, object]:
	index = {}
	for row in doc.get("charge_items") or []:
		if row.get("billing_status") == "Cancelled":
			continue
		for key in get_charge_item_identity_keys(row):
			if key:
				index[key] = row
	return index


def get_charge_item_identity_keys(row) -> list[str]:
	keys = []
	if row.get("source_hash"):
		keys.append(row.get("source_hash"))
	if row.get("source_activity"):
		keys.append(row.get("source_activity"))
		if row.get("item"):
			keys.append(f"{row.get('source_activity')}:{row.get('item')}")
	return keys


def get_activity_source_name(activity) -> str:
	return activity.get("activity_reference") or activity.get("name") or str(activity.get("idx") or "")


def get_activity_source_hash(hospitalisation_name: str, activity) -> str:
	source = get_activity_source_name(activity)
	return f"{hospitalisation_name}:{source}:{activity.get('item')}" if source else f"{hospitalisation_name}:{activity.get('activity_type')}:{activity.get('item')}:{activity.get('activity_datetime')}:{activity.get('clinical_notes')}"


def get_activity_charge_lookup_keys(hospitalisation_name: str, activity) -> list[str]:
	source = get_activity_source_name(activity)
	source_hash = get_activity_source_hash(hospitalisation_name, activity)
	keys = [source_hash]
	if source:
		keys.extend([source, f"{source}:{activity.get('item')}"])
	return keys


def build_charge_item_row(doc, activity, source_activity: str, source_hash: str) -> dict:
	qty = flt(activity.get("qty")) or 1
	pricing = resolve_hospitalisation_charge_pricing(doc, activity.get("item"), activity.get("uom")) if doc else {"rate": get_item_rate(activity.get("item")), "pricing_source": None}
	rate = flt(pricing.get("rate"))
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
		"pricing_source": pricing.get("pricing_source"),
		"billing_status": "Pending Invoice",
		"source_hash": source_hash,
		"notes": activity.get("clinical_notes"),
	}


def update_charge_item_from_activity(row, activity, source_activity: str, source_hash: str, doc=None) -> None:
	if row.get("billing_status") in {"Invoiced", "Cancelled"}:
		return
	manual_rate = flt(row.get("rate"))
	values = build_charge_item_row(doc, activity, source_activity, source_hash)
	if manual_rate > 0:
		values["rate"] = manual_rate
		values["amount"] = (flt(values.get("qty")) or 1) * manual_rate
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


def resolve_hospitalisation_charge_pricing(doc, item: str | None, uom: str | None = None) -> dict:
	if not item:
		return {"rate": 0, "pricing_source": None}
	rate = 0
	pricing_source = None
	try:
		from vetedge.services.billing_core import _get_item_selling_rate

		rate = flt(_get_item_selling_rate(item, company=doc.get("company") if doc else None, customer=(doc.get("customer") or doc.get("primary_owner")) if doc else None, branch=(doc.get("service_branch") or doc.get("branch")) if doc else None, uom=uom))
		pricing_source = "Selling Price" if rate > 0 else None
	except Exception:
		rate = 0
	if rate <= 0:
		rate = get_item_rate(item)
		pricing_source = "Item Standard Rate" if rate > 0 else None
	return {"rate": rate, "pricing_source": pricing_source}


@frappe.whitelist()
def get_hospitalisation_medication_item_context(hospitalisation_name: str, item: str, uom: str | None = None) -> dict:
	require_internal_user()
	if not item:
		return {}
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name) if hospitalisation_name else frappe._dict({})
	item_fields = ["item_name", "stock_uom", "is_stock_item", "standard_rate"]
	for optional_field in ("sales_uom", "has_serial_no", "has_batch_no"):
		try:
			if frappe.get_meta("Item").get_field(optional_field):
				item_fields.append(optional_field)
		except Exception:
			pass
	item_doc = frappe.db.get_value("Item", item, item_fields, as_dict=True) or {}
	resolved_uom = uom or item_doc.get("sales_uom") or item_doc.get("stock_uom")
	pricing = resolve_hospitalisation_charge_pricing(doc, item, resolved_uom)
	rate = flt(pricing.get("rate"))
	pricing_source = pricing.get("pricing_source")
	return {
		"item": item,
		"item_name": item_doc.get("item_name") or item,
		"uom": resolved_uom,
		"stock_uom": item_doc.get("stock_uom"),
		"is_stock_item": cint(item_doc.get("is_stock_item")),
		"has_serial_no": cint(item_doc.get("has_serial_no")),
		"has_batch_no": cint(item_doc.get("has_batch_no")),
		"rate": rate,
		"pricing_source": pricing_source,
		"missing_price": 0 if rate > 0 else 1,
	}


def get_charge_description(activity) -> str:
	parts = [activity.get("activity_type"), activity.get("clinical_notes")]
	return " - ".join(str(part) for part in parts if part)


def validate_hospitalisation_charge_prices(doc) -> None:
	missing = []
	for row in doc.get("charge_items") or []:
		if row.get("billing_status") in {"Cancelled", "Invoiced"}:
			continue
		if row.get("item") and flt(row.get("qty")) > 0 and (flt(row.get("rate")) <= 0 or flt(row.get("amount")) <= 0):
			missing.append(row.get("item"))
	if missing:
		frappe.throw("Rate is required before syncing hospitalisation charges to invoice for: " + ", ".join(missing), frappe.ValidationError)


@frappe.whitelist()
def sync_hospitalisation_charges_to_invoice(hospitalisation_name: str) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	return sync_hospitalisation_charges_with_billing_core(hospitalisation_name)


def sync_hospitalisation_charges_with_billing_core(hospitalisation_name: str) -> dict:
	from vetedge.services.billing_core import BILLING_SESSION_DOCTYPE, sync_source_to_billing_session

	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	normalize_hospitalisation_charge_items(doc)
	validate_hospitalisation_charge_prices(doc)
	previous_status = doc.get("status")
	previous_gate_status = doc.get("payment_gate_status")
	previous_gate_message = doc.get("payment_gate_message")

	result = sync_source_to_billing_session(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	invoice = result.get("invoice")
	if invoice:
		doc.sales_invoice = invoice
		doc.invoice_status = get_hospitalisation_invoice_status(frappe.get_doc("Sales Invoice", invoice))

	session_name = result.get("session")
	if session_name and frappe.db.exists(BILLING_SESSION_DOCTYPE, session_name):
		session = frappe.get_doc(BILLING_SESSION_DOCTYPE, session_name)
		apply_billing_session_charge_statuses_to_hospitalisation(doc, session)

	doc.status = previous_status
	doc.payment_gate_status = previous_gate_status
	doc.payment_gate_message = previous_gate_message
	doc.save()
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
	frappe.throw(
		"Hospitalisation charge invoices must be synced through VetEdge Billing Core.",
		frappe.ValidationError,
	)


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
	charge_keys = set(get_charge_item_identity_keys(charge))
	for activity in doc.get("activities") or []:
		activity_keys = set(get_activity_charge_lookup_keys(doc.name, activity))
		if activity_keys.intersection(charge_keys):
			activity.billing_status = "Charged"
			return


@frappe.whitelist()
def get_hospitalisation_stock_posting_preview(hospitalisation_name: str, activity_row_name: str | None = None) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	if doc.get("status") == "Cancelled":
		frappe.throw("Cancelled hospitalisations cannot post stock usage.", frappe.ValidationError)

	activities = get_stock_posting_activities(doc, activity_row_name)
	summary = {
		"hospitalisation": doc.name,
		"to_post_count": 0,
		"skipped_count": 0,
		"blocked_count": 0,
		"items": [],
		"skipped": [],
		"blocked": [],
		"warnings": [],
	}
	for activity in activities:
		result = preview_single_hospitalisation_activity_stock(doc, activity)
		if result.get("status") == "ready":
			summary["to_post_count"] += 1
			summary["items"].append(result)
		elif result.get("status") == "blocked":
			summary["blocked_count"] += 1
			summary["blocked"].append(result)
		else:
			summary["skipped_count"] += 1
			summary["skipped"].append(result)
	return summary


def preview_single_hospitalisation_activity_stock(doc, activity) -> dict:
	activity_name = get_activity_source_name(activity)
	base = {
		"activity": activity_name,
		"activity_type": activity.get("activity_type"),
		"item": activity.get("item"),
		"qty": flt(activity.get("qty")),
		"uom": activity.get("uom"),
	}
	if not cint(activity.get("stock_affecting")):
		return {**base, "status": "skipped", "message": "Activity is not marked stock affecting."}
	if activity.get("stock_status") == "Posted" or activity.get("stock_entry"):
		return {**base, "status": "skipped", "message": "Stock has already been posted for this activity.", "stock_entry": activity.get("stock_entry")}
	if not activity.get("item"):
		return {**base, "status": "blocked", "message": "A stock Item is required before stock usage can be posted."}
	qty = flt(activity.get("qty"))
	if qty <= 0:
		return {**base, "status": "blocked", "message": "Stock quantity must be greater than zero."}
	try:
		profile = get_hospitalisation_activity_item_stock_profile(activity.get("item"))
		if not profile.is_stock_item:
			return {**base, "status": "blocked", "message": f"Item {activity.get('item')} is not a stock item."}
		warehouse = resolve_hospitalisation_activity_source_warehouse(doc, activity)
	except Exception as exc:
		return {**base, "status": "blocked", "message": str(exc)}
	if not warehouse:
		return {**base, "status": "blocked", "message": "A source warehouse is required before stock usage can be posted."}
	return {**base, "status": "ready", "message": "Ready to post stock usage.", "warehouse": warehouse, "uom": activity.get("uom") or profile.stock_uom}


@frappe.whitelist()
def post_hospitalisation_activity_stock(hospitalisation_name: str, activity_row_name: str | None = None) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	if doc.get("status") == "Cancelled":
		frappe.throw("Cancelled hospitalisations cannot post stock usage.", frappe.ValidationError)

	activities = get_stock_posting_activities(doc, activity_row_name)
	summary = {
		"hospitalisation": doc.name,
		"posted_count": 0,
		"skipped_count": 0,
		"blocked_count": 0,
		"stock_entries": [],
		"messages": [],
	}
	for activity in activities:
		result = post_single_hospitalisation_activity_stock(doc, activity)
		summary["messages"].append(result)
		if result.get("status") == "posted":
			summary["posted_count"] += 1
			if result.get("stock_entry"):
				summary["stock_entries"].append(result.get("stock_entry"))
		elif result.get("status") == "blocked":
			summary["blocked_count"] += 1
		else:
			summary["skipped_count"] += 1

	doc.save()
	return summary


def get_stock_posting_activities(doc, activity_row_name: str | None = None) -> list:
	activities = list(doc.get("activities") or [])
	if not activity_row_name:
		return activities
	for activity in activities:
		if get_activity_source_name(activity) == activity_row_name or activity.get("name") == activity_row_name:
			return [activity]
	frappe.throw(f"Hospitalisation activity row {activity_row_name} was not found.", frappe.ValidationError)


def post_single_hospitalisation_activity_stock(doc, activity) -> dict:
	activity_name = get_activity_source_name(activity)
	if not cint(activity.get("stock_affecting")):
		return update_activity_stock_message(activity, activity_name, "skipped", "Activity is not marked stock affecting.")
	if activity.get("stock_status") == "Posted" or activity.get("stock_entry"):
		return update_activity_stock_message(activity, activity_name, "skipped", "Stock has already been posted for this activity.", activity.get("stock_entry"))
	if not activity.get("item"):
		activity.stock_status = "Pending"
		return update_activity_stock_message(activity, activity_name, "blocked", "A stock Item is required before stock usage can be posted.")
	qty = flt(activity.get("qty"))
	if qty <= 0:
		activity.stock_status = "Pending"
		return update_activity_stock_message(activity, activity_name, "blocked", "Stock quantity must be greater than zero.")

	try:
		profile = get_hospitalisation_activity_item_stock_profile(activity.get("item"))
		if not profile.is_stock_item:
			activity.stock_status = "Pending"
			return update_activity_stock_message(activity, activity_name, "blocked", f"Item {activity.get('item')} is not a stock item.")
		warehouse = resolve_hospitalisation_activity_source_warehouse(doc, activity)
		if not warehouse:
			activity.stock_status = "Pending"
			return update_activity_stock_message(activity, activity_name, "blocked", "A source warehouse is required before stock usage can be posted.")
		entry_name = create_hospitalisation_activity_stock_entry(doc, activity, profile, warehouse, qty)
	except Exception as exc:
		activity.stock_status = "Pending"
		return update_activity_stock_message(activity, activity_name, "blocked", str(exc))

	activity.stock_status = "Posted"
	activity.stock_entry = entry_name
	activity.source_warehouse = warehouse
	activity.posted_stock_qty = qty
	activity.stock_posted_on = now()
	activity.stock_posted_by = frappe.session.user
	return update_activity_stock_message(activity, activity_name, "posted", f"Posted stock usage via Stock Entry {entry_name}.", entry_name)


def get_hospitalisation_activity_item_stock_profile(item_code: str):
	from vetedge.services.stock import get_item_stock_profile

	return get_item_stock_profile(item_code)


def resolve_hospitalisation_activity_source_warehouse(doc, activity) -> str | None:
	warehouse = activity.get("source_warehouse")
	if warehouse:
		from vetedge.services.stock import validate_warehouse_company

		validate_warehouse_company(warehouse, doc.get("company"))
		return warehouse

	from vetedge.services.stock import get_branch_dispensary_warehouse

	warehouse = get_branch_dispensary_warehouse(doc.get("service_branch"), company=doc.get("company"), required=False)
	if warehouse:
		return warehouse

	warehouse = get_hospitalisation_settings_default_warehouse()
	if warehouse:
		from vetedge.services.stock import validate_warehouse_company

		validate_warehouse_company(warehouse, doc.get("company"))
		return warehouse

	return get_company_default_warehouse(doc.get("company"))


def get_hospitalisation_settings_default_warehouse() -> str | None:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
		return None
	meta = frappe.get_meta(SETTINGS_DOCTYPE)
	for fieldname in (
		"hospitalisation_stock_warehouse",
		"default_hospitalisation_stock_warehouse",
		"default_stock_warehouse",
		"default_warehouse",
		"dispensary_warehouse",
	):
		if meta.has_field(fieldname):
			warehouse = frappe.get_single(SETTINGS_DOCTYPE).get(fieldname)
			if warehouse:
				return warehouse
	return None


def get_company_default_warehouse(company: str | None) -> str | None:
	if not company or not frappe.db.exists("DocType", "Company"):
		return None
	meta = frappe.get_meta("Company")
	if not meta.has_field("default_warehouse"):
		return None
	warehouse = frappe.db.get_value("Company", company, "default_warehouse")
	if warehouse:
		from vetedge.services.stock import validate_warehouse_company

		validate_warehouse_company(warehouse, company)
	return warehouse


def create_hospitalisation_activity_stock_entry(doc, activity, profile, warehouse: str, qty: float) -> str:
	from vetedge.services.expiry_control import allocate_item_batches
	from vetedge.services.stock import build_stock_entry_rows, validate_stock_availability

	if not doc.get("company"):
		frappe.throw("Company is required before hospitalisation stock usage can be posted.", frappe.ValidationError)

	allocations = []
	posting_datetime = get_datetime(activity.get("activity_datetime")) if activity.get("activity_datetime") else None
	if profile.has_batch_no:
		allocations = allocate_item_batches(
			item_code=activity.get("item"),
			warehouse=warehouse,
			qty=qty,
			posting_datetime=posting_datetime,
		)
	stock_rows = [
		{
			"item_code": activity.get("item"),
			"qty": qty,
			"uom": activity.get("uom") or profile.stock_uom,
			"batch_allocations": allocations,
		}
	]
	validate_stock_availability(stock_rows, warehouse, posting_datetime=posting_datetime)
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"purpose": "Material Issue",
			"company": doc.get("company"),
			"from_warehouse": warehouse,
			"remarks": f"VetEdge hospitalisation stock usage for {doc.name} activity {get_activity_source_name(activity)}",
			"items": build_stock_entry_rows(
				items=stock_rows,
				warehouse=warehouse,
				company=doc.get("company"),
				use_serial_batch_fields=cint(frappe.get_single_value("Stock Settings", "use_serial_batch_fields")),
			),
		}
	)
	meta = frappe.get_meta("Stock Entry")
	if doc.get("service_branch") and meta.has_field("branch"):
		entry.branch = doc.get("service_branch")
	for fieldname in ("veterinary_hospitalisation", "hospitalisation", "vetedge_hospitalisation"):
		if meta.has_field(fieldname):
			entry.set(fieldname, doc.name)
			break
	entry.insert()
	entry.submit()
	return entry.name


def update_activity_stock_message(activity, activity_name: str, status: str, message: str, stock_entry: str | None = None) -> dict:
	activity.stock_posting_message = message
	return {
		"activity": activity_name,
		"status": status,
		"message": message,
		"stock_entry": stock_entry,
	}


@frappe.whitelist()
def get_hospitalisation_charge_summary(hospitalisation_name: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	pending = invoiced = cancelled = 0
	missing_price_count = 0
	not_billable_count = 0
	for activity in doc.get("activities") or []:
		if not cint(activity.get("billable")):
			not_billable_count += 1
	for row in doc.get("charge_items") or []:
		qty = flt(row.get("qty")) or 1
		rate = flt(row.get("rate"))
		amount = flt(row.get("amount")) or qty * rate
		if row.get("billing_status") == "Invoiced":
			invoiced += amount
		elif row.get("billing_status") == "Cancelled":
			cancelled += amount
		else:
			pending += amount
			if row.get("item") and (rate <= 0 or amount <= 0):
				missing_price_count += 1
	total = pending + invoiced + cancelled
	return {
		"hospitalisation": doc.name,
		"total_pending": pending,
		"total_invoiced": invoiced,
		"total_cancelled": cancelled,
		"total_charge_amount": total,
		"pending_charge_amount": pending,
		"invoiced_charge_amount": invoiced,
		"cancelled_charge_amount": cancelled,
		"not_billable_count": not_billable_count,
		"missing_price_count": missing_price_count,
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


def update_payment_gate_fields(doc, result: dict, save: bool = True) -> None:
	doc.payment_gate_status = result.get("status") or ("Allowed" if result.get("can_proceed") else "Blocked")
	doc.payment_gate_message = result.get("message")
	if doc.get("sales_invoice") and frappe.db.exists("Sales Invoice", doc.sales_invoice):
		doc.invoice_status = get_hospitalisation_invoice_status(frappe.get_doc("Sales Invoice", doc.sales_invoice))
	if save:
		doc.save()


@frappe.whitelist()
def get_hospitalisation_discharge_readiness(hospitalisation_name: str) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	return build_hospitalisation_discharge_readiness(doc)


def build_hospitalisation_discharge_readiness(doc, discharge_summary: str | None = None) -> dict:
	pending_billable = get_pending_billable_activities_without_charges(doc)
	pending_charges = get_pending_hospitalisation_charge_items(doc)
	pending_stock = get_pending_stock_activities(doc)
	billing_session_summary, gate = get_hospitalisation_discharge_billing_state(doc)
	messages = []
	recommended_actions = []

	if not (discharge_summary or doc.get("discharge_summary")):
		messages.append("Discharge summary is required before discharge.")
		recommended_actions.append("Complete Discharge Summary")
	if pending_billable:
		messages.append("There are billable activities that have not been added to the charge sheet.")
		recommended_actions.append("Build Charge Sheet")
	if pending_charges:
		messages.append("There are charge items pending invoice sync.")
		recommended_actions.append("Sync Charges to Invoice")
	if pending_stock:
		messages.append("There are stock-affecting activities that have not been posted.")
		recommended_actions.append("Post Stock Usage")
	if not gate.get("can_proceed"):
		messages.append(gate.get("message") or "Billing/payment gate blocks discharge.")
		recommended_actions.append("Open Billing & Payment")
	elif gate.get("message"):
		messages.append(gate.get("message"))
		if flt((billing_session_summary or {}).get("outstanding_amount")) > 0:
			recommended_actions.append("Open Billing & Payment")

	recommended_actions = list(dict.fromkeys(recommended_actions))
	can_discharge = bool(discharge_summary or doc.get("discharge_summary")) and not pending_billable and not pending_charges and bool(gate.get("can_proceed"))
	return {
		"hospitalisation": doc.name,
		"status": doc.get("status"),
		"pending_billable_activities": pending_billable,
		"pending_charge_items": pending_charges,
		"pending_stock_activities": pending_stock,
		"billing_session": billing_session_summary,
		"invoice_summary": get_hospitalisation_invoice_summary(doc, billing_session_summary),
		"payment_gate": gate,
		"can_discharge": can_discharge,
		"warnings": messages,
		"messages": messages,
		"recommended_actions": recommended_actions,
		"discharge_billing_status": get_discharge_billing_status(pending_billable, pending_charges, billing_session_summary, gate),
	}


def get_pending_billable_activities_without_charges(doc) -> list[dict]:
	charge_sources = {row.get("source_activity") for row in doc.get("charge_items") or [] if row.get("billing_status") != "Cancelled"}
	charge_hashes = {row.get("source_hash") for row in doc.get("charge_items") or [] if row.get("billing_status") != "Cancelled"}
	pending = []
	for activity in doc.get("activities") or []:
		if not cint(activity.get("billable")) or activity.get("billing_status") in {"Charged", "Cancelled"}:
			continue
		source = get_activity_source_name(activity)
		if source not in charge_sources and get_activity_source_hash(doc.name, activity) not in charge_hashes:
			pending.append({"activity": source, "activity_type": activity.get("activity_type"), "item": activity.get("item")})
	return pending


def get_pending_hospitalisation_charge_items(doc) -> list[dict]:
	pending = []
	for row in doc.get("charge_items") or []:
		if row.get("billing_status") in {"Invoiced", "Cancelled"}:
			continue
		pending.append({"charge": row.get("name") or row.get("source_activity"), "item": row.get("item"), "amount": flt(row.get("amount")), "billing_status": row.get("billing_status")})
	return pending


def get_pending_stock_activities(doc) -> list[dict]:
	return [
		{"activity": get_activity_source_name(row), "activity_type": row.get("activity_type"), "item": row.get("item"), "stock_status": row.get("stock_status")}
		for row in doc.get("activities") or []
		if cint(row.get("stock_affecting")) and row.get("stock_status") != "Posted" and not row.get("stock_entry")
	]


def get_hospitalisation_discharge_billing_state(doc) -> tuple[dict | None, dict]:
	try:
		from vetedge.services.billing_core import get_billing_session_summary, get_payment_gate_status, resolve_billing_session

		session = resolve_billing_session(HOSPITALISATION_DOCTYPE, doc.name)
		if session:
			return get_billing_session_summary(session), get_payment_gate_status(session)
	except Exception:
		pass
	gate = evaluate_hospitalisation_payment_gate(doc)
	return None, gate


def get_hospitalisation_invoice_summary(doc, billing_session_summary: dict | None = None) -> dict:
	if billing_session_summary:
		return {
			"current_draft_invoice": billing_session_summary.get("current_draft_invoice"),
			"latest_invoice": billing_session_summary.get("latest_invoice"),
			"outstanding_amount": billing_session_summary.get("outstanding_amount"),
			"payment_status": billing_session_summary.get("payment_status"),
			"invoices": billing_session_summary.get("invoices") or [],
		}
	if doc.get("sales_invoice") and frappe.db.exists("Sales Invoice", doc.sales_invoice):
		invoice = frappe.get_doc("Sales Invoice", doc.sales_invoice)
		return {
			"latest_invoice": invoice.name,
			"docstatus": cint(invoice.docstatus),
			"outstanding_amount": flt(invoice.get("outstanding_amount")),
			"payment_status": get_invoice_payment_status(invoice),
		}
	return {}


def get_discharge_billing_status(pending_billable, pending_charges, billing_session_summary, gate) -> str:
	if pending_billable:
		return "Pending Charges"
	if pending_charges or ((billing_session_summary or {}).get("invoice_ledger") or {}).get("has_pending_uninvoiced_charges"):
		return "Pending Invoice"
	if not gate.get("can_proceed"):
		return "Unpaid"
	if flt((billing_session_summary or {}).get("outstanding_amount")) > 0:
		return "Partially Paid"
	return "Cleared"


def normalize_discharge_details(discharge_summary=None, discharge_details=None) -> dict:
	details = frappe.parse_json(discharge_details) if isinstance(discharge_details, str) and discharge_details else (discharge_details or {})
	if discharge_summary and not details.get("discharge_summary"):
		details["discharge_summary"] = discharge_summary
	return details


@frappe.whitelist()
def admit_hospitalisation(hospitalisation_name: str) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	from vetedge.services.billing_core import get_billing_session_summary, get_payment_gate_status, sync_source_to_billing_session

	source_doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	billing_result = sync_source_to_billing_session(HOSPITALISATION_DOCTYPE, source_doc.name)
	session_name = billing_result.get("session")
	session = frappe.get_doc("Veterinary Billing Session", session_name) if session_name else None

	# Billing Core sync can update hospitalisation compatibility fields.
	# Re-fetch before saving gate/admit fields so check_if_latest sees the
	# current modified timestamp instead of the pre-sync document.
	gate_doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	gate = get_payment_gate_status(session) if session else evaluate_hospitalisation_payment_gate(gate_doc)
	update_payment_gate_fields(gate_doc, gate, save=False)
	invoice = billing_result.get("invoice")
	if invoice:
		gate_doc.sales_invoice = invoice
		gate_doc.invoice_status = get_hospitalisation_invoice_status(frappe.get_doc("Sales Invoice", invoice))
	gate_doc.save()

	response = {
		**gate,
		"allowed": bool(gate.get("can_proceed")),
		"blocked": not bool(gate.get("can_proceed")),
		"open_billing_modal": not bool(gate.get("can_proceed")),
		"hospitalisation_mutated": True,
		"reload_required": True,
		"hospitalisation": gate_doc.name,
		"invoice": invoice,
		"billing_session": session_name,
		"billing_session_summary": get_billing_session_summary(session) if session else None,
	}
	if not gate.get("can_proceed"):
		return response

	admit_doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	admit_doc.status = "Admitted" if admit_doc.status == "Draft" else "Under Care"
	admit_doc.admitted_by = frappe.session.user
	admit_doc.save()
	response["status"] = admit_doc.status
	response["payment_gate_status"] = admit_doc.payment_gate_status
	response["hospitalisation_status"] = admit_doc.status
	return response


@frappe.whitelist()
def discharge_hospitalisation(hospitalisation_name: str, discharge_summary: str | None = None, discharge_details=None, force: bool = False) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	if doc.get("status") == "Cancelled":
		frappe.throw("Cancelled hospitalisations cannot be discharged.", frappe.ValidationError)
	if doc.get("status") == "Discharged":
		frappe.throw("Hospitalisation is already discharged.", frappe.ValidationError)
	if doc.status not in DISCHARGE_ALLOWED_STATUSES:
		frappe.throw("Only admitted hospitalisations can be discharged.", frappe.ValidationError)

	details = normalize_discharge_details(discharge_summary, discharge_details)
	summary = details.get("discharge_summary") or doc.get("discharge_summary")
	if not summary:
		frappe.throw("Discharge summary is required before discharge.", frappe.ValidationError)

	readiness = build_hospitalisation_discharge_readiness(doc, discharge_summary=summary)
	if not readiness.get("can_discharge") and not cint(force):
		doc.discharge_billing_status = readiness.get("discharge_billing_status")
		doc.discharge_message = " ".join(readiness.get("messages") or [])[:1000]
		doc.save()
		frappe.throw(doc.discharge_message or "Hospitalisation is not ready for discharge.", frappe.ValidationError)

	doc.status = "Discharged"
	doc.discharged_by = frappe.session.user
	doc.discharge_datetime = now()
	doc.discharge_summary = summary
	for fieldname in ("condition_at_discharge", "discharge_instructions", "follow_up_date", "follow_up_notes"):
		if fieldname in details:
			doc.set(fieldname, details.get(fieldname))
	doc.discharge_billing_status = "Override" if cint(force) and not readiness.get("can_discharge") else readiness.get("discharge_billing_status")
	doc.discharge_message = " ".join(readiness.get("messages") or [])[:1000]
	doc.save()
	return {"hospitalisation": doc.name, "status": doc.status, "discharge_billing_status": doc.get("discharge_billing_status"), "readiness": readiness}
