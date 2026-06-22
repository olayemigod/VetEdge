from __future__ import annotations

from datetime import timedelta
import uuid

import frappe
from frappe import _dict
from frappe.utils import cint, flt, formatdate, get_datetime, getdate, now, nowdate

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
CARE_LOCATION_DOCTYPE = "Veterinary Care Location"
CARE_LOCATION_LOG_DOCTYPE = "Veterinary Care Location Occupancy Log"
ACTIVE_CARE_LOCATION_STATUSES = {"Available", "Occupied"}
HOSPITALISATION_INITIAL_SOURCE_LINKED_CONSULTATION = "Linked Consultation Billing Session"
HOSPITALISATION_INITIAL_SOURCE_ADMISSION_FEE = "Admission Fee Item"
HOSPITALISATION_INITIAL_SOURCE_DAY_ONE = "Day 1 Daily Charge"
HOSPITALISATION_INITIAL_SOURCE_MANUAL = "Manual Initial Charge"
HOSPITALISATION_INITIAL_SOURCE_NONE = "None"




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


def get_hospitalisation_admission_settings() -> _dict:
	settings = frappe.get_single(SETTINGS_DOCTYPE) if frappe.db.exists("DocType", SETTINGS_DOCTYPE) else _dict()
	meta = frappe.get_meta(SETTINGS_DOCTYPE) if frappe.db.exists("DocType", SETTINGS_DOCTYPE) else None

	def value(fieldname, default=None):
		if meta and not meta.has_field(fieldname):
			return default
		return settings.get(fieldname) if settings.get(fieldname) not in (None, "") else default

	return _dict(
		requires_consultation=cint(value("hospitalisation_requires_consultation", 1)),
		allow_direct_admission=cint(value("allow_direct_hospitalisation_admission", 0)),
		initial_billing_source=value("hospitalisation_initial_billing_source", HOSPITALISATION_INITIAL_SOURCE_LINKED_CONSULTATION),
		admission_fee_item=value("hospitalisation_admission_fee_item"),
		admission_fee_uom=value("hospitalisation_admission_fee_uom"),
	)


def blocked_admission_response(doc, message: str, *, open_billing_modal: bool = False, invoice: str | None = None) -> dict:
	return {
		"allowed": False,
		"blocked": True,
		"can_proceed": False,
		"status": "Blocked",
		"message": message,
		"reload_required": True,
		"open_billing_modal": open_billing_modal,
		"open_invoice_name": invoice,
		"invoice": invoice,
		"hospitalisation": doc.name,
	}


def get_admission_fee_source_key(doc, item: str) -> str:
	return f"admission-fee::{doc.name}::{item}"


def find_charge_item_by_source(doc, source_key: str):
	return next((row for row in doc.get("charge_items") or [] if row.get("billing_status") != "Cancelled" and (row.get("source_key") == source_key or row.get("source_hash") == source_key or row.get("source_activity") == source_key)), None)


def has_real_hospitalisation_charge_or_invoice(doc) -> bool:
	if doc.get("sales_invoice") and frappe.db.exists("Sales Invoice", doc.get("sales_invoice")):
		return True
	for row in doc.get("charge_items") or []:
		if row.get("billing_status") != "Cancelled" and row.get("item") and flt(row.get("amount")) > 0:
			return True
	return False


def has_existing_billing_session_for_hospitalisation_context(doc) -> bool:
	customer = doc.get("customer")
	patient = doc.get("patient") or doc.get("animal")
	if not customer or not patient:
		return False
	try:
		meta = frappe.get_meta("Veterinary Billing Session")
		filters = {"status": ("in", ["Active", "Partially Paid", "Paid"])}
		if meta.has_field("customer"):
			filters["customer"] = customer
		if meta.has_field("animal"):
			filters["animal"] = patient
		elif meta.has_field("patient"):
			filters["patient"] = patient
		else:
			return False
		rows = frappe.get_all("Veterinary Billing Session", filters=filters, fields=["name"], limit=1)
	except Exception:
		return False
	return bool(rows)


def ensure_hospitalisation_admission_fee_charge(doc, settings) -> dict:
	item = settings.get("admission_fee_item")
	if not item:
		return blocked_admission_response(doc, "Configure a Hospitalisation Admission Fee Item before admission.")
	source_key = get_admission_fee_source_key(doc, item)
	row = find_charge_item_by_source(doc, source_key)
	if row and row.get("billing_status") == "Invoiced":
		return {"created_or_resolved": True}
	uom = settings.get("admission_fee_uom") or get_item_uom(item)
	pricing = resolve_hospitalisation_charge_pricing(doc, item, uom)
	rate = flt(pricing.get("rate"))
	if rate <= 0:
		return blocked_admission_response(doc, "Rate is required for the configured Hospitalisation Admission Fee Item before admission.")
	values = {
		"source_activity": source_key,
		"source_key": source_key,
		"source_hash": source_key,
		"activity_type": "Admission Fee",
		"charge_category": "Manual",
		"item": item,
		"item_name": get_item_name(item),
		"description": "Hospitalisation Admission Fee",
		"qty": 1,
		"uom": uom,
		"rate": rate,
		"amount": rate,
		"pricing_source": pricing.get("pricing_source"),
		"billing_status": "Pending Invoice",
		"notes": "Initial hospitalisation admission billing source",
	}
	if row:
		if row.get("billing_status") != "Invoiced":
			for fieldname, value in values.items():
				setattr(row, fieldname, value)
	else:
		append_charge_item(doc, values)
	doc.save()
	return {"created_or_resolved": True}


def ensure_hospitalisation_day_one_charge(doc) -> dict:
	charge_date = getdate(doc.get("admission_datetime") or nowdate())
	result = generate_hospitalisation_daily_charges(doc.name, from_date=charge_date, to_date=charge_date, care_level=doc.get("care_level") or "Standard")
	if result.get("created") or result.get("updated") or result.get("skipped_existing"):
		if result.get("missing_price"):
			return blocked_admission_response(doc, "Rate is required for the Day 1 Daily Charge before admission.")
		return {"created_or_resolved": True, "daily_charge": result}
	return blocked_admission_response(doc, result.get("message") or "Daily charge item is not configured for this care level.")


def resolve_hospitalisation_initial_billing_source(doc, gate: str) -> dict:
	settings = get_hospitalisation_admission_settings()
	if settings.requires_consultation and not doc.get("linked_consultation") and not settings.allow_direct_admission:
		return blocked_admission_response(doc, "Hospitalisation should be created from a Consultation. Link a Consultation or enable Direct Hospitalisation Admission.")
	source = settings.initial_billing_source or HOSPITALISATION_INITIAL_SOURCE_LINKED_CONSULTATION
	if source == HOSPITALISATION_INITIAL_SOURCE_NONE:
		if gate != NO_PAYMENT_GATE:
			return blocked_admission_response(doc, "Hospitalisation Initial Billing Source cannot be None when Full or Partial payment gate is enabled.")
		return {"created_or_resolved": False}
	if source == HOSPITALISATION_INITIAL_SOURCE_LINKED_CONSULTATION:
		if doc.get("linked_consultation") or has_existing_billing_session_for_hospitalisation_context(doc):
			return {"created_or_resolved": True}
		if gate != NO_PAYMENT_GATE:
			return blocked_admission_response(doc, "Link a Consultation before admission or choose another Hospitalisation Initial Billing Source.")
		return {"created_or_resolved": False}
	if source == HOSPITALISATION_INITIAL_SOURCE_ADMISSION_FEE:
		return ensure_hospitalisation_admission_fee_charge(doc, settings)
	if source == HOSPITALISATION_INITIAL_SOURCE_DAY_ONE:
		return ensure_hospitalisation_day_one_charge(doc)
	if source == HOSPITALISATION_INITIAL_SOURCE_MANUAL:
		if not has_real_hospitalisation_charge_or_invoice(doc):
			return blocked_admission_response(doc, "Add a Manual Initial Charge before admission.")
		return {"created_or_resolved": True}
	return {"created_or_resolved": False}


def validate_hospitalisation(doc) -> None:
	if doc.is_new():
		assert_hospitalisation_enabled()
	sync_hospitalisation_title(doc)
	validate_locked_hospitalisation_charge_items(doc)
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
		if row.get("billing_status") == "Invoiced" and row.get("sales_invoice") and is_sales_invoice_submitted_or_paid(row.get("sales_invoice")):
			continue
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


def is_sales_invoice_submitted_or_paid(invoice_name: str | None) -> bool:
	if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
		return False
	invoice = frappe.db.get_value("Sales Invoice", invoice_name, ["docstatus", "status", "outstanding_amount"], as_dict=True) or {}
	return cint(invoice.get("docstatus")) == 1 or invoice.get("status") == "Paid" or flt(invoice.get("outstanding_amount")) <= 0 and cint(invoice.get("docstatus")) == 1


def validate_locked_hospitalisation_charge_items(doc) -> None:
	if not getattr(doc, "get_doc_before_save", None):
		return
	old = doc.get_doc_before_save()
	if not old:
		return
	old_rows = {row.name: row for row in old.get("charge_items") or [] if row.get("name")}
	financial_fields = ("item", "qty", "uom", "rate", "amount")
	for row in doc.get("charge_items") or []:
		old_row = old_rows.get(row.get("name"))
		if not old_row:
			continue
		locked = old_row.get("billing_status") == "Invoiced" and old_row.get("sales_invoice") and is_sales_invoice_submitted_or_paid(old_row.get("sales_invoice"))
		if not locked:
			continue
		if any(row.get(fieldname) != old_row.get(fieldname) for fieldname in financial_fields):
			frappe.throw("This charge is already invoiced. Create an adjustment charge instead.", frappe.ValidationError)


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
	if row.get("source_key"):
		keys.append(row.get("source_key"))
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
	added_count = result.get("added_count", 0)
	updated_count = result.get("updated_count", 0)
	return {
		"hospitalisation": hospitalisation_name,
		"updated": bool(invoice and (added_count or updated_count or not result.get("created"))),
		"invoice": invoice,
		"open_invoice_name": invoice,
		"added_count": added_count,
		"updated_count": updated_count,
		"skipped_count": 0,
		"created_new_invoice": bool(result.get("created")),
		"billing_session": session_name,
		"reload_required": True,
		"message": f"Updated draft Sales Invoice {invoice}." if invoice and not result.get("created") else (f"Created draft Sales Invoice {invoice}." if invoice else "No pending hospitalisation charges to invoice."),
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


CARE_LEVEL_OPTIONS = {"Standard", "Observation", "Intensive Care", "ICU", "Isolation", "Recovery"}


def get_hospitalisation_branch(doc) -> str | None:
	return doc.get("service_branch") or doc.get("branch")


def get_care_location_branch(location) -> str | None:
	return location.get("branch")


def get_active_care_location_occupancy_count(care_location: str, exclude_hospitalisation: str | None = None) -> int:
	filters = {"care_location": care_location, "status": "Active"}
	logs = frappe.get_all(
		CARE_LOCATION_LOG_DOCTYPE,
		filters=filters,
		fields=["name", "hospitalisation"],
	) or []
	count = 0
	for row in logs:
		hospitalisation = row.get("hospitalisation")
		if exclude_hospitalisation and hospitalisation == exclude_hospitalisation:
			continue
		if hospitalisation and frappe.db.exists(HOSPITALISATION_DOCTYPE, hospitalisation):
			status = frappe.db.get_value(HOSPITALISATION_DOCTYPE, hospitalisation, "status")
			if status in {"Cancelled", "Discharged"}:
				continue
		count += 1
	return count


def get_active_care_location_log(hospitalisation_name: str, care_location: str | None = None):
	filters = {"hospitalisation": hospitalisation_name, "status": "Active"}
	if care_location:
		filters["care_location"] = care_location
	logs = frappe.get_all(
		CARE_LOCATION_LOG_DOCTYPE,
		filters=filters,
		fields=["name"],
		order_by="assigned_on desc",
		limit=1,
	) or []
	return logs[0].get("name") if logs else None


def update_care_location_status(care_location: str) -> dict:
	location = frappe.get_doc(CARE_LOCATION_DOCTYPE, care_location)
	capacity = max(cint(location.get("capacity")) or 1, 1)
	active_count = get_active_care_location_occupancy_count(care_location)
	if not cint(location.get("enabled")) or location.get("status") in {"Inactive", "Maintenance", "Cleaning"}:
		return {"care_location": care_location, "capacity": capacity, "active_occupancy_count": active_count, "available_slots": max(capacity - active_count, 0), "status": location.get("status")}
	new_status = "Occupied" if active_count >= capacity else "Available"
	if location.get("status") != new_status:
		location.status = new_status
		location.save()
	return {"care_location": care_location, "capacity": capacity, "active_occupancy_count": active_count, "available_slots": max(capacity - active_count, 0), "status": new_status}


def ensure_care_location_assignable(doc, location) -> dict:
	if doc.get("status") == "Cancelled":
		frappe.throw("Cancelled hospitalisations cannot be assigned a care location.", frappe.ValidationError)
	if not cint(location.get("enabled")) or location.get("status") in {"Inactive", "Maintenance", "Cleaning"}:
		frappe.throw("Selected care location is not available for assignment.", frappe.ValidationError)
	doc_branch = get_hospitalisation_branch(doc)
	location_branch = get_care_location_branch(location)
	if doc_branch and location_branch and doc_branch != location_branch:
		frappe.throw("Care location branch does not match the hospitalisation branch.", frappe.ValidationError)
	capacity = max(cint(location.get("capacity")) or 1, 1)
	active_count = get_active_care_location_occupancy_count(location.name, exclude_hospitalisation=doc.name)
	if active_count >= capacity:
		frappe.throw("Selected care location is already full.", frappe.ValidationError)
	return {"capacity": capacity, "active_occupancy_count": active_count, "available_slots": capacity - active_count}


@frappe.whitelist()
def assign_hospitalisation_care_location(hospitalisation_name: str, care_location: str, notes: str | None = None) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	location = frappe.get_doc(CARE_LOCATION_DOCTYPE, care_location)
	availability = ensure_care_location_assignable(doc, location)
	previous_location = doc.get("care_location")
	if previous_location and previous_location != care_location:
		release_hospitalisation_care_location(hospitalisation_name, notes="Released before reassignment.")
		doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	assigned_on = now()
	doc.care_location = care_location
	doc.care_location_assigned_on = assigned_on
	doc.care_location_released_on = None
	doc.care_location_status = "Assigned"
	doc.save()
	log_name = get_active_care_location_log(doc.name, care_location)
	if log_name:
		log = frappe.get_doc(CARE_LOCATION_LOG_DOCTYPE, log_name)
		log.notes = notes or log.get("notes")
		log.save()
	else:
		log = frappe.get_doc({
			"doctype": CARE_LOCATION_LOG_DOCTYPE,
			"hospitalisation": doc.name,
			"patient": doc.get("patient"),
			"pet_owner": doc.get("customer") or doc.get("primary_owner"),
			"care_location": care_location,
			"branch": get_hospitalisation_branch(doc) or location.get("branch"),
			"assigned_on": assigned_on,
			"status": "Active",
			"assigned_by": frappe.session.user,
			"notes": notes,
		})
		log.insert()
	status = update_care_location_status(care_location)
	return {"hospitalisation": doc.name, "care_location": care_location, "assigned": True, "message": "Care location assigned.", **availability, **status}


@frappe.whitelist()
def release_hospitalisation_care_location(hospitalisation_name: str, notes: str | None = None) -> dict:
	require_internal_user()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	care_location = doc.get("care_location")
	if not care_location:
		return {"hospitalisation": doc.name, "released": False, "message": "No care location is assigned."}
	released_on = now()
	log_name = get_active_care_location_log(doc.name, care_location)
	if log_name:
		log = frappe.get_doc(CARE_LOCATION_LOG_DOCTYPE, log_name)
		log.status = "Released"
		log.released_on = released_on
		log.released_by = frappe.session.user
		log.notes = notes or log.get("notes")
		log.save()
	doc.care_location_released_on = released_on
	doc.care_location_status = "Released"
	doc.care_location = None
	doc.save()
	status = update_care_location_status(care_location)
	return {"hospitalisation": doc.name, "care_location": care_location, "released": True, "message": "Care location released.", **status}


@frappe.whitelist()
def get_available_care_locations(branch: str | None = None, location_type: str | None = None, care_level: str | None = None) -> list[dict]:
	require_internal_user()
	filters = {"enabled": 1}
	if branch:
		filters["branch"] = branch
	if location_type:
		filters["location_type"] = location_type
	locations = frappe.get_all(
		CARE_LOCATION_DOCTYPE,
		filters=filters,
		fields=["name", "location_name", "branch", "location_type", "status", "capacity", "enabled"],
		order_by="location_name asc",
	) or []
	available = []
	for row in locations:
		if row.get("status") in {"Inactive", "Maintenance", "Cleaning"}:
			continue
		capacity = max(cint(row.get("capacity")) or 1, 1)
		active_count = get_active_care_location_occupancy_count(row.get("name"))
		available_slots = max(capacity - active_count, 0)
		if available_slots <= 0:
			continue
		available.append({
			"name": row.get("name"),
			"location_name": row.get("location_name") or row.get("name"),
			"branch": row.get("branch"),
			"location_type": row.get("location_type"),
			"status": row.get("status"),
			"capacity": capacity,
			"active_occupancy_count": active_count,
			"available_slots": available_slots,
			"care_level": care_level,
		})
	return available


def get_hospitalisation_charge_dates(doc, from_date=None, to_date=None) -> list:
	start = getdate(from_date or doc.get("admission_datetime") or nowdate())
	end_source = to_date or (doc.get("discharge_datetime") if doc.get("status") == "Discharged" else None) or nowdate()
	end = getdate(end_source)
	if end < start:
		end = start
	dates = []
	current = start
	while current <= end:
		dates.append(current)
		current = current + timedelta(days=1)
	return dates


def get_hospitalisation_daily_charge_setting(care_level: str):
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	for row in settings.get("hospitalisation_daily_charge_settings") or []:
		if cint(row.get("enabled")) and row.get("care_level") == care_level:
			return row
	return None


def get_daily_charge_source_key(hospitalisation_name: str, charge_date, care_level: str, item: str) -> str:
	return f"daily-stay::{hospitalisation_name}::{getdate(charge_date)}::{care_level}::{item}"


def get_daily_charge_index(doc) -> dict[str, object]:
	index = {}
	for row in doc.get("charge_items") or []:
		if row.get("billing_status") == "Cancelled":
			continue
		key = row.get("source_key") or row.get("source_hash")
		if key:
			index[key] = row
	return index


def build_daily_charge_row(doc, setting, charge_date, care_level: str, source_key: str) -> dict:
	qty = flt(setting.get("qty_per_day")) or 1
	uom = setting.get("uom") or get_item_uom(setting.get("item"))
	pricing = resolve_hospitalisation_charge_pricing(doc, setting.get("item"), uom)
	rate = flt(pricing.get("rate"))
	description = setting.get("description") or f"{care_level} Hospitalisation - {formatdate(charge_date)}"
	return {
		"source_activity": source_key,
		"source_key": source_key,
		"source_hash": source_key,
		"activity_type": "Daily Stay",
		"charge_category": "Daily Stay",
		"charge_date": getdate(charge_date),
		"care_level": care_level,
		"item": setting.get("item"),
		"item_name": get_item_name(setting.get("item")),
		"description": description,
		"qty": qty,
		"uom": uom,
		"rate": rate,
		"amount": qty * rate,
		"pricing_source": pricing.get("pricing_source"),
		"billing_status": "Pending Invoice",
		"notes": description,
	}


@frappe.whitelist()
def generate_hospitalisation_daily_charges(hospitalisation_name: str, from_date=None, to_date=None, care_level: str | None = None) -> dict:
	require_internal_user()
	assert_hospitalisation_enabled()
	doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, hospitalisation_name)
	if doc.is_new() if callable(getattr(doc, "is_new", None)) else not doc.get("name"):
		frappe.throw("Save the hospitalisation before generating daily charges.", frappe.ValidationError)
	if doc.get("status") == "Cancelled":
		frappe.throw("Cancelled hospitalisations cannot generate daily charges.", frappe.ValidationError)
	selected_care_level = care_level or doc.get("care_level") or "Standard"
	if selected_care_level not in CARE_LEVEL_OPTIONS:
		selected_care_level = "Standard"
	setting = get_hospitalisation_daily_charge_setting(selected_care_level)
	if not setting:
		return {
			"hospitalisation": doc.name,
			"created": 0,
			"updated": 0,
			"skipped_existing": 0,
			"missing_price": 0,
			"total_amount": 0,
			"message": f"Daily charge item is not configured for {selected_care_level} care level.",
		}
	charge_dates = get_hospitalisation_charge_dates(doc, from_date=from_date, to_date=to_date)
	index = get_daily_charge_index(doc)
	created = updated = skipped_existing = missing_price = 0
	total_amount = 0
	for charge_date in charge_dates:
		source_key = get_daily_charge_source_key(doc.name, charge_date, selected_care_level, setting.get("item"))
		row = index.get(source_key)
		if row and row.get("billing_status") == "Invoiced":
			skipped_existing += 1
			total_amount += flt(row.get("amount"))
			continue
		new_values = build_daily_charge_row(doc, setting, charge_date, selected_care_level, source_key)
		if row:
			manual_rate = flt(row.get("rate"))
			for fieldname, value in new_values.items():
				if fieldname in {"rate", "amount"} and manual_rate > 0:
					continue
				setattr(row, fieldname, value)
			if manual_rate > 0:
				row.amount = (flt(row.get("qty")) or 1) * manual_rate
			updated += 1
		else:
			append_charge_item(doc, new_values)
			created += 1
			row = doc.get("charge_items")[-1]
		if flt(row.get("rate")) <= 0 or flt(row.get("amount")) <= 0:
			missing_price += 1
		total_amount += flt(row.get("amount"))
	doc.save()
	return {
		"hospitalisation": doc.name,
		"created": created,
		"updated": updated,
		"skipped_existing": skipped_existing,
		"missing_price": missing_price,
		"total_amount": total_amount,
		"message": f"Generated {created} daily hospitalisation charges.",
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
	if doc.get("care_location"):
		messages.append("Care location is still assigned. Release it when the patient physically leaves the location.")
		recommended_actions.append("Release Care Location")
	if not gate.get("can_proceed"):
		messages.append(gate.get("message") or "Billing/payment gate blocks discharge.")
		recommended_actions.append("Open Billing & Payment")
	elif gate.get("message"):
		messages.append(gate.get("message"))
		if flt((billing_session_summary or {}).get("outstanding_amount")) > 0:
			recommended_actions.append("Open Billing & Payment")

	recommended_actions = list(dict.fromkeys(recommended_actions))
	can_discharge = bool(discharge_summary or doc.get("discharge_summary")) and not pending_billable and not pending_charges and not pending_stock and bool(gate.get("can_proceed"))
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
		if cint(row.get("stock_affecting")) and row.get("stock_status") not in {"Posted", "Not Applicable"} and not row.get("stock_entry")
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
	gate_mode = get_hospitalisation_payment_gate()
	initial_result = resolve_hospitalisation_initial_billing_source(source_doc, gate_mode)
	if initial_result.get("blocked"):
		return initial_result
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
	if readiness.get("pending_stock_activities"):
		return {
			"blocked": True,
			"reload_required": True,
			"reason": "pending_stock_posting",
			"message": "Stock usage must be posted before discharge. Use Stock → Post Stock Usage.",
			"open_stock_action": True,
			"hospitalisation": doc.name,
			"status": doc.get("status"),
			"readiness": readiness,
		}
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
