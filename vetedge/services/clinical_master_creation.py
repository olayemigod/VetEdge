from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, flt

from vetedge.services.portal_access import require_internal_user


SETTINGS_DOCTYPE = "Veterinary Settings"
TREATMENT_ITEM_DOCTYPE = "Veterinary Treatment Item"
CREATE_PREFIX = "__vetedge_create__:"
ITEM_CREATE_PREFIX = "__vetedge_create_erpnext_item__:"
CONTEXTS = {"consultation", "hospitalisation"}
KIND_SETTINGS = {
	"symptom": "allow_new_symptoms_in_clinical_workflow",
	"diagnosis": "allow_new_diagnoses_in_clinical_workflow",
	"treatment_item": "allow_new_treatment_items_in_clinical_workflow",
}
PRICING_ROLES = {"System Manager", "VetEdge Administrator", "Branch Manager", "Accounts Manager"}
ITEM_CREATE_ROLES = {"System Manager", "Stock Manager", "Stock User"}


def _clean(value: Any) -> str:
	return str(value or "").strip()


def _normalise_context(context: str | None) -> str:
	resolved = _clean(context).lower() or "consultation"
	if resolved not in CONTEXTS:
		frappe.throw(_("Unsupported clinical creation context."), frappe.ValidationError)
	return resolved


def _settings_meta_has(fieldname: str) -> bool:
	try:
		return bool(frappe.get_meta(SETTINGS_DOCTYPE).has_field(fieldname))
	except Exception:
		return False


def _setting_enabled(fieldname: str) -> bool:
	if not frappe.db.exists("DocType", SETTINGS_DOCTYPE) or not _settings_meta_has(fieldname):
		return False
	return bool(cint(frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)))


def _roles() -> set[str]:
	try:
		return set(frappe.get_roles(frappe.session.user) or [])
	except Exception:
		return set()


def _can_manage_pricing() -> bool:
	return bool(_roles() & PRICING_ROLES)


def _can_create_erpnext_item() -> bool:
	if not _setting_enabled("allow_erpnext_item_creation_from_treatment"):
		return False
	if not (_roles() & ITEM_CREATE_ROLES):
		return False
	try:
		return bool(frappe.has_permission("Item", ptype="create"))
	except Exception:
		return False


def _kind_doctype(kind: str) -> str:
	return {
		"symptom": "Veterinary Symptom",
		"diagnosis": "Veterinary Diagnosis",
		"treatment_item": TREATMENT_ITEM_DOCTYPE,
	}.get(kind, "")


def _kind_allowed(kind: str, context: str) -> bool:
	fieldname = KIND_SETTINGS.get(kind)
	if not fieldname or not _setting_enabled(fieldname):
		return False
	if context == "hospitalisation" and not _setting_enabled("allow_clinical_master_creation_in_hospitalisation"):
		return False
	doctype = _kind_doctype(kind)
	if not doctype:
		return False
	try:
		return bool(frappe.has_permission(doctype, ptype="create"))
	except Exception:
		return False


def _resolved_price_list(branch: str | None = None, company: str | None = None, customer: str | None = None) -> str | None:
	try:
		from vetedge.services.billing_core import _resolve_selling_price_list

		return _resolve_selling_price_list(company=company, customer=customer, branch=branch)
	except Exception:
		return None


@frappe.whitelist()
def get_clinical_master_creation_capabilities(
	context: str = "consultation",
	branch: str | None = None,
	company: str | None = None,
	customer: str | None = None,
) -> dict[str, Any]:
	require_internal_user()
	resolved_context = _normalise_context(context)
	return {
		"context": resolved_context,
		"can_create_symptom": _kind_allowed("symptom", resolved_context),
		"can_create_diagnosis": _kind_allowed("diagnosis", resolved_context),
		"can_create_treatment_item": _kind_allowed("treatment_item", resolved_context),
		"can_create_erpnext_item": _can_create_erpnext_item(),
		"can_select_price_list": _can_manage_pricing(),
		"resolved_price_list": _resolved_price_list(branch=branch, company=company, customer=customer),
	}


def _matches_exact(rows: list[dict[str, Any]], query: str) -> bool:
	needle = _clean(query).casefold()
	if not needle:
		return True
	for row in rows:
		for fieldname in ("value", "label"):
			if _clean(row.get(fieldname)).casefold() == needle:
				return True
	return False


def _create_value(kind: str, query: str) -> str:
	return f"{CREATE_PREFIX}{kind}:{_clean(query)}"


def parse_create_value(value: str | None, kind: str) -> str | None:
	prefix = f"{CREATE_PREFIX}{kind}:"
	raw = _clean(value)
	if raw.startswith(prefix):
		return raw[len(prefix):].strip()
	return None


def _append_create_option(
	rows: list[dict[str, Any]],
	*,
	kind: str,
	query: str,
	context: str,
	branch: str | None = None,
) -> list[dict[str, Any]]:
	if not _clean(query) or _matches_exact(rows, query) or not _kind_allowed(kind, context):
		return rows
	label = {
		"symptom": _("Create New Symptom: {0}").format(query),
		"diagnosis": _("Create New Diagnosis: {0}").format(query),
		"treatment_item": _("Create New Treatment Item: {0}").format(query),
	}[kind]
	return [*rows, {"value": _create_value(kind, query), "label": f"+ {label}", "create_new": 1, "kind": kind}]


def search_clinical_master_options(
	kind: str,
	search: str = "",
	*,
	context: str = "consultation",
	branch: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	require_internal_user()
	resolved_context = _normalise_context(context)
	query = _clean(search)
	page_len = min(max(cint(limit) or 20, 1), 50)

	if kind == "treatment_item":
		from vetedge.services.treatment_items import get_treatment_item_link_options

		rows = [
			{"value": row[0], "label": row[1] or row[0]}
			for row in get_treatment_item_link_options("Item", query, "name", 0, page_len, {})
		]
		return _append_create_option(rows, kind=kind, query=query, context=resolved_context, branch=branch)

	if kind not in {"symptom", "diagnosis"}:
		frappe.throw(_("Unsupported clinical master search."), frappe.ValidationError)

	doctype = _kind_doctype(kind)
	meta = frappe.get_meta(doctype)
	title_field = meta.title_field or ("symptom_name" if kind == "symptom" else "diagnosis_name")
	fields = ["name"]
	if title_field != "name" and meta.has_field(title_field):
		fields.append(title_field)
	filters: dict[str, Any] = {}
	if meta.has_field("disabled"):
		filters["disabled"] = 0
	or_filters = [[doctype, fieldname, "like", f"%{query}%"] for fieldname in fields] if query else None
	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		order_by=f"{title_field if title_field in fields else 'name'} asc",
		page_length=page_len,
	)
	options = [{"value": row.get("name"), "label": row.get(title_field) or row.get("name")} for row in rows]
	return _append_create_option(options, kind=kind, query=query, context=resolved_context, branch=branch)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_treatment_item_link_options_with_create(doctype, txt, searchfield, start, page_len, filters):
	"""Native Frappe Link query: curated Treatment Items plus a gated create-if-missing option."""
	require_internal_user()
	from vetedge.services.treatment_items import get_treatment_item_link_options

	rows = [
		{"value": row[0], "label": row[1] or row[0]}
		for row in get_treatment_item_link_options(doctype, txt, searchfield, start, page_len, filters)
	]
	if cint(start):
		return [[row["value"], row["label"]] for row in rows]
	rows = _append_create_option(
		rows,
		kind="treatment_item",
		query=_clean(txt),
		context="consultation",
	)
	return [[row["value"], row["label"]] for row in rows]


def _has_exact_treatment_profile(query: str) -> bool:
	needle = _clean(query)
	if not needle:
		return True
	filters = {"item": needle}
	if frappe.get_meta(TREATMENT_ITEM_DOCTYPE).has_field("disabled"):
		filters["disabled"] = 0
	if frappe.db.exists(TREATMENT_ITEM_DOCTYPE, filters):
		return True
	item_code = frappe.db.get_value("Item", {"item_name": needle, "disabled": 0}, "name")
	return bool(item_code and frappe.db.exists(TREATMENT_ITEM_DOCTYPE, {"item": item_code, "disabled": 0}))


def append_hospitalisation_item_create_option(
	rows: list[dict[str, Any]],
	query: str,
	*,
	branch: str | None = None,
) -> list[dict[str, Any]]:
	if (
		not _clean(query)
		or _has_exact_treatment_profile(query)
		or not _kind_allowed("treatment_item", "hospitalisation")
	):
		return rows
	label = _("Create New Treatment Item: {0}").format(query)
	return [
		*rows,
		{
			"value": _create_value("treatment_item", query),
			"label": f"+ {label}",
			"create_new": 1,
			"kind": "treatment_item",
		},
	]


def _search_link_options(
	doctype: str,
	search: str,
	*,
	filters: dict[str, Any] | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	meta = frappe.get_meta(doctype)
	title_field = meta.title_field or "name"
	fields = ["name"]
	if title_field != "name" and meta.has_field(title_field):
		fields.append(title_field)
	resolved_filters = dict(filters or {})
	if meta.has_field("disabled") and "disabled" not in resolved_filters:
		resolved_filters["disabled"] = 0
	query = _clean(search)
	or_filters = [[doctype, fieldname, "like", f"%{query}%"] for fieldname in fields] if query else None
	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=resolved_filters,
		or_filters=or_filters,
		order_by=f"{title_field if title_field in fields else 'name'} asc",
		page_length=min(max(cint(limit) or 20, 1), 50),
	)
	return [{"value": row.get("name"), "label": row.get(title_field) or row.get("name")} for row in rows]


@frappe.whitelist()
def search_clinical_creation_options(
	kind: str,
	search: str = "",
	context: str = "consultation",
	branch: str | None = None,
	company: str | None = None,
	customer: str | None = None,
	limit: int = 20,
) -> list[dict[str, Any]]:
	require_internal_user()
	resolved_context = _normalise_context(context)
	query = _clean(search)
	capabilities = get_clinical_master_creation_capabilities(
		resolved_context,
		branch=branch,
		company=company,
		customer=customer,
	)

	if kind == "erpnext_item":
		rows = frappe.get_list(
			"Item",
			fields=["name", "item_name", "stock_uom", "is_stock_item"],
			filters={"disabled": 0},
			or_filters=[
				["Item", "name", "like", f"%{query}%"],
				["Item", "item_name", "like", f"%{query}%"],
			] if query else None,
			order_by="item_name asc, name asc",
			page_length=min(max(cint(limit) or 20, 1), 50),
		)
		options = [
			{
				"value": row.get("name"),
				"label": row.get("item_name") or row.get("name"),
				"description": " · ".join(filter(None, [row.get("stock_uom"), _("Stock Item") if cint(row.get("is_stock_item")) else _("Service Item")])),
			}
			for row in rows
		]
		if query and capabilities["can_create_erpnext_item"] and not _matches_exact(options, query):
			options.append({
				"value": f"{ITEM_CREATE_PREFIX}{query}",
				"label": f"+ { _('Create New ERPNext Item: {0}').format(query) }",
				"create_new": 1,
				"kind": "erpnext_item",
			})
		return options

	if kind == "diagnosis_category":
		return _search_link_options("Veterinary Diagnosis Category", query, limit=limit)
	if kind == "service_type":
		return _search_link_options("Veterinary Service Type", query, limit=limit)
	if kind == "treatment_type":
		return _search_link_options("Veterinary Treatment Type", query, limit=limit)
	if kind == "item_group":
		return _search_link_options("Item Group", query, filters={"is_group": 0}, limit=limit)
	if kind == "uom":
		return _search_link_options("UOM", query, limit=limit)
	if kind == "price_list":
		resolved = capabilities.get("resolved_price_list")
		if not capabilities["can_select_price_list"]:
			return [{"value": resolved, "label": resolved}] if resolved else []
		return _search_link_options("Price List", query, filters={"enabled": 1, "selling": 1}, limit=limit)

	frappe.throw(_("Unsupported clinical creation option type."), frappe.ValidationError)


def _assert_exact_duplicate_absent(doctype: str, fieldname: str, value: str, label: str) -> None:
	if frappe.db.exists(doctype, {fieldname: value}):
		frappe.throw(_("{0} already exists. Select the existing record instead.").format(label), frappe.DuplicateEntryError)


def _validate_selling_price_list(price_list: str | None) -> None:
	if not price_list:
		return
	if not frappe.db.exists("Price List", price_list):
		frappe.throw(_("Selected Price List does not exist."), frappe.ValidationError)
	row = frappe.db.get_value("Price List", price_list, ["enabled", "selling"], as_dict=True) or {}
	if not cint(row.get("enabled")) or not cint(row.get("selling")):
		frappe.throw(_("Select an enabled selling Price List."), frappe.ValidationError)


def _existing_item_price(item_code: str, price_list: str | None) -> dict[str, Any]:
	if not price_list or not frappe.db.exists("DocType", "Item Price"):
		return {}
	row = frappe.db.get_value(
		"Item Price",
		{"item_code": item_code, "price_list": price_list},
		["name", "price_list_rate"],
		as_dict=True,
	)
	return dict(row or {})


def _create_erpnext_item(values: dict[str, Any]) -> str:
	if not _can_create_erpnext_item():
		frappe.throw(_("You are not permitted to create ERPNext Items from the clinical workflow."), frappe.PermissionError)

	item_name = _clean(values.get("item_name"))
	item_code = _clean(values.get("item_code")) or item_name
	item_group = _clean(values.get("item_group"))
	stock_uom = _clean(values.get("stock_uom"))
	if not item_name or not item_code or not item_group or not stock_uom:
		frappe.throw(_("Item Name, Item Code, Item Group and Stock UOM are required."), frappe.ValidationError)
	if frappe.db.exists("Item", item_code):
		frappe.throw(_("ERPNext Item {0} already exists. Select it instead.").format(item_code), frappe.DuplicateEntryError)
	if not frappe.db.exists("Item Group", item_group):
		frappe.throw(_("Selected Item Group does not exist."), frappe.ValidationError)
	if not frappe.db.exists("UOM", stock_uom):
		frappe.throw(_("Selected Stock UOM does not exist."), frappe.ValidationError)

	meta = frappe.get_meta("Item")
	payload: dict[str, Any] = {
		"doctype": "Item",
		"item_code": item_code,
		"item_name": item_name,
		"item_group": item_group,
		"stock_uom": stock_uom,
	}
	for fieldname, value in {
		"is_stock_item": cint(values.get("is_stock_item", 1)),
		"is_sales_item": 1,
		"disabled": 0,
	}.items():
		if meta.has_field(fieldname):
			payload[fieldname] = value

	doc = frappe.get_doc(payload)
	doc.insert()
	return doc.name


def _create_symptom(values: dict[str, Any]) -> dict[str, Any]:
	name = _clean(values.get("name") or values.get("symptom_name"))
	if not name:
		frappe.throw(_("Symptom Name is required."), frappe.ValidationError)
	_assert_exact_duplicate_absent("Veterinary Symptom", "symptom_name", name, _("Symptom"))
	doc = frappe.get_doc({
		"doctype": "Veterinary Symptom",
		"symptom_name": name,
		"body_system": _clean(values.get("body_system")) or None,
		"description": _clean(values.get("description")) or None,
		"disabled": 0,
	})
	doc.insert()
	return {"name": doc.name, "value": doc.name, "label": doc.get("symptom_name") or doc.name}


def _create_diagnosis(values: dict[str, Any]) -> dict[str, Any]:
	name = _clean(values.get("name") or values.get("diagnosis_name"))
	if not name:
		frappe.throw(_("Diagnosis Name is required."), frappe.ValidationError)
	_assert_exact_duplicate_absent("Veterinary Diagnosis", "diagnosis_name", name, _("Diagnosis"))
	category = _clean(values.get("category"))
	if category and not frappe.db.exists("Veterinary Diagnosis Category", category):
		frappe.throw(_("Selected Diagnosis Category does not exist."), frappe.ValidationError)
	doc = frappe.get_doc({
		"doctype": "Veterinary Diagnosis",
		"diagnosis_name": name,
		"category": category or None,
		"description": _clean(values.get("description")) or None,
		"disabled": 0,
	})
	doc.insert()
	return {"name": doc.name, "value": doc.name, "label": doc.get("diagnosis_name") or doc.name}


def _create_treatment_item(
	values: dict[str, Any],
	*,
	branch: str | None = None,
	company: str | None = None,
	customer: str | None = None,
) -> dict[str, Any]:
	item_code = _clean(values.get("item"))
	new_item = values.get("new_item") if isinstance(values.get("new_item"), dict) else {}
	if not item_code and new_item:
		item_code = _create_erpnext_item(new_item)
	if not item_code:
		frappe.throw(_("Select an ERPNext Item or create a new one."), frappe.ValidationError)
	if not frappe.db.exists("Item", item_code):
		frappe.throw(_("Selected ERPNext Item does not exist."), frappe.ValidationError)

	item_doc = frappe.get_doc("Item", item_code)
	item_doc.check_permission("read")
	if cint(item_doc.get("disabled")):
		frappe.throw(_("Disabled ERPNext Items cannot be used as Treatment Items."), frappe.ValidationError)
	if frappe.db.exists(TREATMENT_ITEM_DOCTYPE, {"item": item_code}):
		frappe.throw(_("A Veterinary Treatment Item already exists for {0}. Select it instead.").format(item_code), frappe.DuplicateEntryError)

	resolved_price_list = _resolved_price_list(branch=branch, company=company, customer=customer)
	requested_price_list = _clean(values.get("price_list"))
	if requested_price_list and requested_price_list != (resolved_price_list or "") and not _can_manage_pricing():
		frappe.throw(_("You are not permitted to override the contextual Price List."), frappe.PermissionError)
	price_list = requested_price_list or resolved_price_list
	_validate_selling_price_list(price_list)

	default_price = flt(values.get("default_price") or 0)
	if default_price < 0:
		frappe.throw(_("Default Price cannot be negative."), frappe.ValidationError)
	existing_price = _existing_item_price(item_code, price_list)
	if (
		existing_price
		and default_price > 0
		and flt(existing_price.get("price_list_rate")) != default_price
		and not _can_manage_pricing()
	):
		frappe.throw(
			_("An Item Price already exists for this Item and Price List. You are not permitted to overwrite it."),
			frappe.PermissionError,
		)

	service_type = _clean(values.get("service_type"))
	treatment_type = _clean(values.get("treatment_type"))
	if service_type and not frappe.db.exists("Veterinary Service Type", service_type):
		frappe.throw(_("Selected Service Type does not exist."), frappe.ValidationError)
	if treatment_type and not frappe.db.exists("Veterinary Treatment Type", treatment_type):
		frappe.throw(_("Selected Treatment Type does not exist."), frappe.ValidationError)

	doc = frappe.get_doc({
		"doctype": TREATMENT_ITEM_DOCTYPE,
		"item": item_code,
		"price_list": price_list,
		"default_price": default_price,
		"service_type": service_type or None,
		"treatment_type": treatment_type or None,
		"shelf_life_in_days": max(cint(values.get("shelf_life_in_days") or 0), 0),
		"description": _clean(values.get("description")) or None,
		"disabled": 0,
	})
	doc.insert()

	from vetedge.services.treatment_items import get_treatment_item_defaults_for_consultation

	defaults = get_treatment_item_defaults_for_consultation(
		item_code,
		company=company,
		customer=customer,
		branch=branch,
	)
	return {
		"name": doc.name,
		"value": item_code,
		"label": item_doc.get("item_name") or item_code,
		"item": item_code,
		"price_list": price_list,
		"defaults": defaults,
	}


@frappe.whitelist()
def create_clinical_master(
	kind: str,
	values: dict[str, Any] | str | None = None,
	context: str = "consultation",
	branch: str | None = None,
	company: str | None = None,
	customer: str | None = None,
) -> dict[str, Any]:
	require_internal_user()
	resolved_context = _normalise_context(context)
	if kind not in KIND_SETTINGS:
		frappe.throw(_("Unsupported clinical master type."), frappe.ValidationError)
	if not _kind_allowed(kind, resolved_context):
		frappe.throw(
			_("Creating new {0} records from this clinical workflow is disabled or not permitted.").format(kind.replace("_", " ")),
			frappe.PermissionError,
		)

	payload = values or {}
	if isinstance(payload, str):
		payload = frappe.parse_json(payload)
	if not isinstance(payload, dict):
		frappe.throw(_("Expected creation values as a JSON object."), frappe.ValidationError)

	if kind == "symptom":
		return _create_symptom(payload)
	if kind == "diagnosis":
		return _create_diagnosis(payload)
	return _create_treatment_item(
		payload,
		branch=branch,
		company=company,
		customer=customer,
	)
