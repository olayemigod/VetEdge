from __future__ import annotations

import frappe
from frappe.utils import flt


STANDARD_SELLING_PRICE_LIST = "Standard Selling"


def sync_master_item_price(
	doc,
	item_field: str,
	price_field: str,
	price_list_field: str = "price_list",
) -> str | None:
	item_code = doc.get(item_field)
	rate = doc.get(price_field)
	if not item_code or rate in (None, ""):
		return None
	rate = flt(rate)
	if rate <= 0:
		return None
	price_list = resolve_master_price_list(doc.get(price_list_field))
	if not price_list:
		return None
	currency = get_price_list_currency(price_list)
	uom = get_item_stock_uom(item_code)
	return upsert_item_price(item_code, price_list, rate, currency=currency, uom=uom)


def resolve_master_price_list(price_list: str | None = None) -> str | None:
	if price_list:
		return price_list
	for resolver in (
		get_vetedge_default_selling_price_list,
		get_erpnext_default_selling_price_list,
		get_standard_selling_price_list,
	):
		value = resolver()
		if value:
			return value
	return None


def get_vetedge_default_selling_price_list() -> str | None:
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return None
	if not doctype_has_field("Veterinary Settings", "default_selling_price_list"):
		return None
	return frappe.db.get_single_value("Veterinary Settings", "default_selling_price_list")


def get_erpnext_default_selling_price_list() -> str | None:
	if not frappe.db.exists("DocType", "Selling Settings"):
		return None
	if not doctype_has_field("Selling Settings", "selling_price_list"):
		return None
	return frappe.db.get_single_value("Selling Settings", "selling_price_list")


def get_standard_selling_price_list() -> str | None:
	if frappe.db.exists("Price List", STANDARD_SELLING_PRICE_LIST):
		return STANDARD_SELLING_PRICE_LIST
	return None


def get_price_list_currency(price_list: str) -> str | None:
	try:
		if doctype_has_field("Price List", "currency"):
			return frappe.db.get_value("Price List", price_list, "currency")
	except Exception:
		return None
	return None


def get_item_stock_uom(item_code: str) -> str | None:
	try:
		return frappe.db.get_value("Item", item_code, "stock_uom")
	except Exception:
		return None


def upsert_item_price(
	item_code: str,
	price_list: str,
	rate: float,
	currency: str | None = None,
	uom: str | None = None,
) -> str:
	if not frappe.db.exists("DocType", "Item Price"):
		frappe.throw("ERPNext Item Price is required for VetEdge master pricing.", frappe.ValidationError)

	filters = {"item_code": item_code, "price_list": price_list}
	if doctype_has_field("Item Price", "selling"):
		filters["selling"] = 1
	if doctype_has_field("Item Price", "uom"):
		filters["uom"] = uom or ["in", ("", None)]
	if doctype_has_field("Item Price", "currency") and currency:
		filters["currency"] = currency

	existing_name = frappe.db.get_value("Item Price", filters, "name")
	values = {"price_list_rate": flt(rate)}
	if doctype_has_field("Item Price", "selling"):
		values["selling"] = 1
	if doctype_has_field("Item Price", "uom") and uom:
		values["uom"] = uom
	if doctype_has_field("Item Price", "currency") and currency:
		values["currency"] = currency

	if existing_name:
		frappe.db.set_value("Item Price", existing_name, values, update_modified=True)
		return existing_name

	item_price = frappe.get_doc(
		{
			"doctype": "Item Price",
			"item_code": item_code,
			"price_list": price_list,
			**values,
		}
	)
	item_price.insert()
	return item_price.name


def doctype_has_field(doctype: str, fieldname: str) -> bool:
	try:
		meta = frappe.get_meta(doctype)
		get_field = getattr(meta, "get_field", None)
		if get_field:
			return bool(get_field(fieldname))
		has_field = getattr(meta, "has_field", None)
		if has_field:
			return bool(has_field(fieldname))
	except Exception:
		return False
	return False
