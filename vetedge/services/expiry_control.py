from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

import frappe
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime


SETTINGS_DOCTYPE = "Veterinary Settings"
DEFAULT_BATCH_SELECTION_POLICY = "FEFO"


@dataclass(frozen=True)
class ExpiryControlSettings:
	enforce_strict_expiry_control: bool = True
	batch_selection_policy: str = DEFAULT_BATCH_SELECTION_POLICY
	block_manual_expired_batch_override: bool = True


@dataclass(frozen=True)
class BatchAllocation:
	batch_no: str
	qty: float
	expiry_date: str | None
	warehouse: str


def get_expiry_control_settings() -> ExpiryControlSettings:
	try:
		if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
			return ExpiryControlSettings()

		meta = frappe.get_meta(SETTINGS_DOCTYPE)
		settings = frappe.get_single(SETTINGS_DOCTYPE)
	except Exception:
		return ExpiryControlSettings()

	return ExpiryControlSettings(
		enforce_strict_expiry_control=bool(cint(
			settings.get("enforce_strict_expiry_control")
			if meta.has_field("enforce_strict_expiry_control")
			else 1
		)),
		batch_selection_policy=(settings.get("batch_selection_policy") or DEFAULT_BATCH_SELECTION_POLICY)
		if meta.has_field("batch_selection_policy")
		else DEFAULT_BATCH_SELECTION_POLICY,
		block_manual_expired_batch_override=bool(cint(
			settings.get("block_manual_expired_batch_override")
			if meta.has_field("block_manual_expired_batch_override")
			else 1
		)),
	)


def get_available_valid_batches(
	item_code: str,
	warehouse: str,
	posting_datetime=None,
):
	from erpnext.stock.doctype.batch.batch import get_available_batches

	posting_datetime = get_datetime(posting_datetime or safe_now_datetime())
	available_batches = get_available_batches(
		frappe._dict(
			{
				"item_code": item_code,
				"warehouse": warehouse,
				"based_on": frappe.get_single_value("Stock Settings", "pick_serial_and_batch_based_on"),
				"posting_datetime": posting_datetime,
				"ignore_reserved_stock": True,
			}
		)
	)
	if not available_batches:
		return []

	batch_meta = {
		row.name: row
		for row in frappe.get_all(
			"Batch",
			filters={"name": ["in", list(available_batches.keys())], "item": item_code, "disabled": 0},
			fields=["name", "expiry_date"],
		)
	}

	valid_batches = []
	for batch_no, qty in OrderedDict(available_batches).items():
		meta = batch_meta.get(batch_no)
		if not meta:
			continue
		valid_batches.append(
			BatchAllocation(
				batch_no=batch_no,
				qty=float(qty),
				expiry_date=meta.get("expiry_date"),
				warehouse=warehouse,
			)
		)

	return valid_batches


def validate_stock_item_expiry_configuration(profile) -> None:
	settings = get_expiry_control_settings()
	if not settings.enforce_strict_expiry_control or not getattr(profile, "is_stock_item", False):
		return

	item_code = getattr(profile, "item_code", "the selected item")
	is_expiry_sensitive = bool(
		getattr(profile, "has_batch_no", False)
		or getattr(profile, "has_expiry_date", False)
		or int(getattr(profile, "shelf_life_in_days", 0) or 0) > 0
	)
	if not is_expiry_sensitive:
		return

	if not getattr(profile, "has_batch_no", False):
		raise_validation(
			f"Item {item_code} is expiry-sensitive but is not configured as a batch-managed ERPNext Item. "
			"Enable Batch No and maintain stock by batch before dispensary confirmation.",
		)

	if not getattr(profile, "has_expiry_date", False):
		raise_validation(
			f"Item {item_code} is expiry-sensitive but does not have ERPNext expiry tracking enabled. "
			"Enable Expiry Date on the Item before dispensary confirmation.",
		)


def allocate_item_batches(
	item_code: str,
	warehouse: str,
	qty: float,
	posting_datetime=None,
	manual_batch_no: str | None = None,
) -> list[BatchAllocation]:
	settings = get_expiry_control_settings()
	if not settings.enforce_strict_expiry_control:
		raise_validation(
			"Strict expiry control is disabled in Veterinary Settings. Outward dispensary stock issues are blocked until strict expiry control is enabled.",
		)
	if (settings.batch_selection_policy or DEFAULT_BATCH_SELECTION_POLICY) != DEFAULT_BATCH_SELECTION_POLICY:
		raise_validation(
			f"Unsupported batch selection policy {settings.batch_selection_policy}. Dispensary currently supports FEFO only.",
		)
	if qty <= 0:
		raise_validation("Dispensed stock quantity must be greater than zero.")

	valid_batches = get_available_valid_batches(item_code, warehouse, posting_datetime=posting_datetime)
	if manual_batch_no:
		return allocate_manual_batch(
			item_code=item_code,
			warehouse=warehouse,
			qty=qty,
			manual_batch_no=manual_batch_no,
			valid_batches=valid_batches,
			settings=settings,
		)

	return allocate_fefo_batches(item_code=item_code, warehouse=warehouse, qty=qty, valid_batches=valid_batches)


def allocate_manual_batch(
	item_code: str,
	warehouse: str,
	qty: float,
	manual_batch_no: str,
	valid_batches: list[BatchAllocation] | None = None,
	settings: ExpiryControlSettings | None = None,
) -> list[BatchAllocation]:
	settings = settings or get_expiry_control_settings()
	valid_batches = valid_batches or get_available_valid_batches(item_code, warehouse)
	selected = next((row for row in valid_batches if row.batch_no == manual_batch_no), None)

	if not selected:
		validate_manual_batch_block(item_code=item_code, warehouse=warehouse, batch_no=manual_batch_no, settings=settings)
		raise_validation(
			f"Batch {manual_batch_no} has no usable non-expired quantity for Item {item_code} in warehouse {warehouse}.",
		)

	if selected.qty < qty:
		raise_validation(
			f"Batch {manual_batch_no} does not have enough non-expired stock for Item {item_code} in warehouse {warehouse}. "
			f"Available {selected.qty}, required {qty}.",
		)

	return [
		BatchAllocation(
			batch_no=selected.batch_no,
			qty=qty,
			expiry_date=selected.expiry_date,
			warehouse=warehouse,
		)
	]


def validate_manual_batch_block(
	item_code: str,
	warehouse: str,
	batch_no: str,
	settings: ExpiryControlSettings | None = None,
) -> None:
	settings = settings or get_expiry_control_settings()
	batch = get_batch_record(batch_no)
	if not batch or batch.item != item_code:
		raise_validation(
			f"Batch {batch_no} is not valid for Item {item_code}.",
		)
	if batch.disabled:
		raise_validation(f"Batch {batch_no} is disabled and cannot be dispensed.")
	if settings.block_manual_expired_batch_override and batch.expiry_date and getdate(batch.expiry_date) <= getdate(safe_now_datetime()):
		raise_validation(
			f"Batch {batch_no} for Item {item_code} expired on {batch.expiry_date} and cannot be dispensed from warehouse {warehouse}.",
		)


def allocate_fefo_batches(
	item_code: str,
	warehouse: str,
	qty: float,
	valid_batches: list[BatchAllocation] | None = None,
) -> list[BatchAllocation]:
	valid_batches = valid_batches or get_available_valid_batches(item_code, warehouse)
	allocations: list[BatchAllocation] = []
	remaining = float(qty)

	for batch in valid_batches:
		if remaining <= 0:
			break

		allocated_qty = min(batch.qty, remaining)
		if allocated_qty <= 0:
			continue

		allocations.append(
			BatchAllocation(
				batch_no=batch.batch_no,
				qty=allocated_qty,
				expiry_date=batch.expiry_date,
				warehouse=warehouse,
			)
		)
		remaining -= allocated_qty

	if remaining > 0:
		raise_validation(
			f"Insufficient non-expired stock for Item {item_code} in warehouse {warehouse}. "
			f"Required {qty}, available {qty - remaining}.",
		)

	return allocations


def summarize_allocations(allocations: list[BatchAllocation]) -> str:
	return ", ".join(
		f"{allocation.batch_no}: {flt(allocation.qty)}"
		for allocation in allocations
	)


def safe_now_datetime():
	try:
		return now_datetime()
	except Exception:
		return datetime.now(UTC).replace(tzinfo=None)


def get_batch_record(batch_no: str):
	return frappe.db.get_value(
		"Batch",
		batch_no,
		["name", "item", "expiry_date", "disabled"],
		as_dict=True,
	)


def raise_validation(message: str) -> None:
	try:
		frappe.throw(message, frappe.ValidationError)
	except Exception:
		raise frappe.ValidationError(message)
