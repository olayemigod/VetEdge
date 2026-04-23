from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe.utils import cint, flt, now_datetime

from vetedge.services.branding import get_clinic_brand_name
from vetedge.services.expiry_control import BatchAllocation

BRANCH_DISPENSARY_WAREHOUSE_FIELD = "vetedge_dispensary_warehouse"
STOCK_ENTRY_CONSULTATION_FIELD = "vetedge_consultation"


@dataclass(frozen=True)
class ItemStockProfile:
	item_code: str
	is_stock_item: bool
	stock_uom: str | None
	item_name: str | None
	disabled: bool
	has_batch_no: bool
	has_expiry_date: bool
	shelf_life_in_days: int


def get_item_stock_profile(item_code: str | None) -> ItemStockProfile:
	if not item_code:
		frappe.throw("Dispensed item must reference an Item.", frappe.ValidationError)

	item = frappe.db.get_value(
		"Item",
		item_code,
		["name", "is_stock_item", "stock_uom", "item_name", "disabled", "has_batch_no", "has_expiry_date", "shelf_life_in_days"],
		as_dict=True,
	)
	if not item:
		frappe.throw(f"Item {item_code} is not a valid ERPNext Item.", frappe.ValidationError)
	if cint(item.disabled):
		frappe.throw(f"Item {item_code} is disabled and cannot be dispensed.", frappe.ValidationError)

	return ItemStockProfile(
		item_code=item.name,
		is_stock_item=bool(cint(item.is_stock_item)),
		stock_uom=item.stock_uom,
		item_name=item.item_name,
		disabled=bool(cint(item.disabled)),
		has_batch_no=bool(cint(item.has_batch_no)),
		has_expiry_date=bool(cint(item.has_expiry_date)),
		shelf_life_in_days=int(item.shelf_life_in_days or 0),
	)


def get_branch_dispensary_warehouse(branch: str | None, company: str | None = None, required: bool = False) -> str | None:
	if not branch:
		if required:
			frappe.throw("A Service Branch is required to resolve the dispensary warehouse.", frappe.ValidationError)
		return None

	if not frappe.db.exists("DocType", "Branch"):
		if required:
			frappe.throw("Branch doctype is unavailable, so dispensary warehouse cannot be resolved.", frappe.ValidationError)
		return None

	branch_meta = frappe.get_meta("Branch")
	fieldnames = [fieldname for fieldname in ("warehouse", BRANCH_DISPENSARY_WAREHOUSE_FIELD) if branch_meta.has_field(fieldname)]
	warehouse = None
	if fieldnames:
		values = frappe.db.get_value("Branch", branch, fieldnames, as_dict=True)
		for fieldname in fieldnames:
			warehouse = (values or {}).get(fieldname)
			if warehouse:
				break

	if not warehouse and required:
		frappe.throw(
			f"Branch {branch} does not have a dispensary warehouse configured.",
			frappe.ValidationError,
		)

	if warehouse:
		validate_warehouse_company(warehouse, company)

	return warehouse


def validate_warehouse_company(warehouse: str | None, company: str | None = None) -> None:
	if not warehouse:
		return

	warehouse_company = frappe.db.get_value("Warehouse", warehouse, "company")
	if not warehouse_company:
		frappe.throw(f"Warehouse {warehouse} is not a valid ERPNext Warehouse.", frappe.ValidationError)
	if company and warehouse_company != company:
		frappe.throw(
			f"Warehouse {warehouse} belongs to {warehouse_company} and cannot be used for company {company}.",
			frappe.ValidationError,
		)


def validate_stock_availability(
	item_rows: list[dict],
	warehouse: str,
	posting_datetime=None,
) -> None:
	if not item_rows:
		return

	from erpnext.stock.utils import get_stock_balance

	posting_datetime = posting_datetime or now_datetime()
	posting_date = posting_datetime.date()
	posting_time = posting_datetime.time()

	for row in item_rows:
		qty = flt(row.get("qty"))
		if qty <= 0:
			frappe.throw("Dispensed stock quantity must be greater than zero.", frappe.ValidationError)

		balance = flt(
			get_stock_balance(
				row["item_code"],
				warehouse,
				posting_date=posting_date,
				posting_time=posting_time,
			)
		)
		if balance < qty:
			frappe.throw(
				f"Insufficient stock for Item {row['item_code']} in warehouse {warehouse}. "
				f"Available {balance}, required {qty}.",
				frappe.ValidationError,
			)


def create_material_issue_stock_entry(
	consultation_name: str,
	company: str,
	warehouse: str,
	items: list[dict],
	branch: str | None = None,
	remarks: str | None = None,
) -> str:
	if not items:
		frappe.throw("At least one stock item is required before creating a dispensary stock issue.", frappe.ValidationError)

	use_serial_batch_fields = cint(frappe.get_single_value("Stock Settings", "use_serial_batch_fields"))
	entry = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Issue",
			"purpose": "Material Issue",
			"company": company,
			"from_warehouse": warehouse,
			"remarks": remarks or f"{get_clinic_brand_name()} dispensary issue for consultation {consultation_name}",
			"items": build_stock_entry_rows(
				items=items,
				warehouse=warehouse,
				company=company,
				use_serial_batch_fields=use_serial_batch_fields,
			),
		}
	)

	meta = frappe.get_meta("Stock Entry")
	if branch and meta.has_field("branch"):
		entry.branch = branch
	if meta.has_field(STOCK_ENTRY_CONSULTATION_FIELD):
		entry.set(STOCK_ENTRY_CONSULTATION_FIELD, consultation_name)

	entry.insert(ignore_permissions=True)
	entry.submit()
	return entry.name


def build_stock_entry_rows(
	items: list[dict],
	warehouse: str,
	company: str,
	use_serial_batch_fields: int = 0,
) -> list[dict]:
	rows: list[dict] = []
	for row in items:
		allocations = row.get("batch_allocations") or []
		if allocations and use_serial_batch_fields:
			for allocation in allocations:
				rows.append(
					make_stock_entry_row(
						row=row,
						warehouse=warehouse,
						allocation=allocation,
						use_serial_batch_fields=1,
					)
				)
			continue

		stock_entry_row = make_stock_entry_row(
			row=row,
			warehouse=warehouse,
			allocation=None,
			use_serial_batch_fields=use_serial_batch_fields,
		)
		if allocations:
			stock_entry_row["serial_and_batch_bundle"] = make_outward_batch_bundle(
				item_code=row["item_code"],
				warehouse=warehouse,
				company=company,
				allocations=allocations,
				qty=flt(row["qty"]),
			)
		rows.append(stock_entry_row)

	return rows


def make_stock_entry_row(
	row: dict,
	warehouse: str,
	allocation: BatchAllocation | dict | None = None,
	use_serial_batch_fields: int = 0,
) -> dict:
	qty = flt(allocation.qty if allocation else row["qty"])
	data = {
		"item_code": row["item_code"],
		"qty": qty,
		"s_warehouse": warehouse,
		"uom": row.get("uom"),
		"stock_uom": row.get("uom"),
		"conversion_factor": 1,
		"basic_rate": 0,
		"use_serial_batch_fields": cint(use_serial_batch_fields),
	}
	if allocation and use_serial_batch_fields:
		data["batch_no"] = allocation.batch_no
	return data


def make_outward_batch_bundle(
	item_code: str,
	warehouse: str,
	company: str,
	allocations: list[BatchAllocation | dict],
	qty: float,
) -> str:
	from erpnext.stock.doctype.batch.batch import make_batch_bundle

	return make_batch_bundle(
		item_code=item_code,
		warehouse=warehouse,
		batches=frappe._dict(
			{
				allocation.batch_no if hasattr(allocation, "batch_no") else allocation["batch_no"]: flt(
					allocation.qty if hasattr(allocation, "qty") else allocation["qty"]
				)
				for allocation in allocations
			}
		),
		company=company,
		type_of_transaction="Outward",
		qty=flt(qty),
	)
