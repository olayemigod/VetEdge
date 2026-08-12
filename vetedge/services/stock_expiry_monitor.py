from __future__ import annotations

from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, flt, getdate, nowdate

from vetedge.services.stock import get_branch_dispensary_warehouse


SETTINGS_DOCTYPE = "Veterinary Settings"
DEFAULT_EXPIRY_REMINDER_DAYS = "30,60,90"
EXPIRY_STATUSES = ("Expired", "Expiring Soon", "Safe")
EXTERNAL_EXPIRY_CHANNELS = ("Email", "WhatsApp", "SMS")
INTERNAL_NOTIFICATION_ROLES = (
	"VetEdge Administrator",
	"VetEdge Dispensary User",
	"Dispensary User",
	"Branch Manager",
	"VetEdge Branch Manager",
)


@dataclass(frozen=True)
class StockExpiryMonitorSettings:
	enable_stock_expiry_monitor: bool = False
	expiry_reminder_days: str = DEFAULT_EXPIRY_REMINDER_DAYS
	enable_internal_expiry_notifications: bool = True
	enable_email_expiry_notifications: bool = False
	enable_whatsapp_expiry_notifications: bool = False
	enable_sms_expiry_notifications: bool = False


def get_stock_expiry_monitor_settings() -> StockExpiryMonitorSettings:
	try:
		if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
			return StockExpiryMonitorSettings()
		meta = frappe.get_meta(SETTINGS_DOCTYPE)
		settings = frappe.get_single(SETTINGS_DOCTYPE)
	except Exception:
		return StockExpiryMonitorSettings()

	def value(fieldname, default=None):
		return settings.get(fieldname) if meta.has_field(fieldname) else default

	return StockExpiryMonitorSettings(
		enable_stock_expiry_monitor=bool(cint(value("enable_stock_expiry_monitor", 0))),
		expiry_reminder_days=cstr(value("expiry_reminder_days", DEFAULT_EXPIRY_REMINDER_DAYS) or DEFAULT_EXPIRY_REMINDER_DAYS),
		enable_internal_expiry_notifications=bool(cint(value("enable_internal_expiry_notifications", 1))),
		enable_email_expiry_notifications=bool(cint(value("enable_email_expiry_notifications", 0))),
		enable_whatsapp_expiry_notifications=bool(cint(value("enable_whatsapp_expiry_notifications", 0))),
		enable_sms_expiry_notifications=bool(cint(value("enable_sms_expiry_notifications", 0))),
	)


def parse_expiry_buckets(value: str | None = None) -> list[int]:
	value = cstr(value or DEFAULT_EXPIRY_REMINDER_DAYS)
	buckets: list[int] = []
	for part in value.replace("\n", ",").split(","):
		part = part.strip()
		if not part:
			continue
		try:
			days = int(part)
		except Exception:
			continue
		if days >= 0 and days not in buckets:
			buckets.append(days)
	return sorted(buckets) or parse_expiry_buckets(DEFAULT_EXPIRY_REMINDER_DAYS)


def classify_expiry(expiry_date, buckets: list[int] | None = None, today=None) -> str:
	if not expiry_date:
		return "Safe"
	today_date = getdate(today or nowdate())
	expiry = getdate(expiry_date)
	if expiry <= today_date:
		return "Expired"
	max_days = max(buckets or parse_expiry_buckets(), default=0)
	if max_days and expiry <= add_days(today_date, max_days):
		return "Expiring Soon"
	return "Safe"


def days_to_expiry(expiry_date, today=None) -> int | None:
	if not expiry_date:
		return None
	return (getdate(expiry_date) - getdate(today or nowdate())).days


def execute_report(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_stock_expiry_rows(filters)
	columns = get_report_columns()
	summary = get_summary(rows)
	chart = get_status_chart(summary)
	return columns, rows, None, chart, summary


def get_report_columns() -> list[dict]:
	return [
		_col("item_code", "Link", "Item", _("Item")),
		_col("item_name", "Data", None, _("Item Name")),
		_col("item_group", "Link", "Item Group", _("Item Group")),
		_col("batch_no", "Link", "Batch", _("Batch")),
		_col("warehouse", "Link", "Warehouse", _("Warehouse")),
		_col("company", "Link", "Company", _("Company")),
		_col("branch", "Link", "Branch", _("Branch")),
		_col("qty", "Float", None, _("Quantity")),
		_col("stock_uom", "Link", "UOM", _("UOM")),
		_col("expiry_date", "Date", None, _("Expiry Date")),
		_col("days_to_expiry", "Int", None, _("Days to Expiry")),
		_col("expiry_status", "Data", None, _("Expiry Status")),
		_col("expiry_bucket", "Data", None, _("Expiry Bucket")),
	]


def get_stock_expiry_rows(filters=None) -> list[dict]:
	filters = frappe._dict(filters or {})
	if not _has_stock_expiry_source():
		return []

	buckets = parse_expiry_buckets(filters.get("expiry_buckets") or _settings_bucket_value())
	today = filters.get("posting_date") or nowdate()
	rows = _query_batch_stock_rows(filters)
	branch_map = _get_warehouse_branch_map(row.get("warehouse") for row in rows)
	result = []

	for row in rows:
		status = classify_expiry(row.get("expiry_date"), buckets=buckets, today=today)
		result.append(
			{
				"item_code": row.get("item_code"),
				"item_name": row.get("item_name"),
				"item_group": row.get("item_group"),
				"batch_no": row.get("batch_no"),
				"warehouse": row.get("warehouse"),
				"company": row.get("company"),
				"branch": branch_map.get(row.get("warehouse")),
				"qty": flt(row.get("qty")),
				"stock_uom": row.get("stock_uom"),
				"expiry_date": row.get("expiry_date"),
				"days_to_expiry": days_to_expiry(row.get("expiry_date"), today=today),
				"expiry_status": status,
				"expiry_bucket": _expiry_bucket_label(row.get("expiry_date"), status, buckets, today=today),
			}
		)

	return sorted(result, key=_expiry_sort_key)


def get_summary(rows: list[dict]) -> list[dict]:
	from vetedge.services.report_insights import build_report_summary

	return build_report_summary("Stock Expiry Status", rows)


def get_status_chart(summary: list[dict]) -> dict:
	values = {row["label"]: row["value"] for row in summary}
	labels = [_("Expired"), _("Expiring Soon"), _("Safe")]
	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Items"), "values": [values.get(label, 0) for label in labels]}],
		},
		"type": "bar",
		"colors": ["#ef4444", "#f59e0b", "#22c55e"],
		"title": _("Stock Expiry Status"),
	}


def generate_stock_expiry_notifications(filters=None) -> dict:
	settings = get_stock_expiry_monitor_settings()
	if not settings.enable_stock_expiry_monitor:
		return {"created": 0, "skipped": "monitor_disabled", "external_skipped": []}

	rows = [
		row for row in get_stock_expiry_rows(filters)
		if row.get("expiry_status") in {"Expired", "Expiring Soon"}
	]
	result = {"created": 0, "reused": 0, "external_skipped": []}

	if settings.enable_internal_expiry_notifications:
		for row in rows:
			for recipient in get_internal_notification_recipients():
				created = _create_internal_stock_expiry_notification(row, recipient)
				if created is True:
					result["created"] += 1
				elif created is False:
					result["reused"] += 1

	for channel, enabled in (
		("Email", settings.enable_email_expiry_notifications),
		("WhatsApp", settings.enable_whatsapp_expiry_notifications),
		("SMS", settings.enable_sms_expiry_notifications),
	):
		if enabled:
			_log_external_channel_skipped(channel)
			result["external_skipped"].append(channel)

	return result


def get_internal_notification_recipients() -> list[str]:
	if not frappe.db.exists("DocType", "Has Role"):
		return []
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(INTERNAL_NOTIFICATION_ROLES)]},
		fields=["parent"],
		distinct=True,
	)
	return sorted(
		{
			row.get("parent")
			for row in users
			if row.get("parent") and row.get("parent") not in {"Guest", "Administrator"}
		}
	)


def _create_internal_stock_expiry_notification(row: dict, recipient: str) -> bool | None:
	try:
		from vetedge.services.notifications import create_notification_item

		status = row.get("expiry_status")
		title = _("Stock {0}: {1}").format(status, row.get("item_code"))
		message = _("{0} batch {1} in {2} is {3}.").format(
			row.get("item_code"),
			row.get("batch_no") or _("No Batch"),
			row.get("warehouse") or _("Unassigned Warehouse"),
			status.lower(),
		)
		result = create_notification_item(
			event_key="stock_expiry_status",
			recipient_user=recipient,
			notification_title=title,
			message=message,
			reference_doctype="Batch" if row.get("batch_no") else "Item",
			reference_name=row.get("batch_no") or row.get("item_code"),
			action_url="/app/query-report/Stock%20Expiry%20Status",
			priority="High" if status == "Expired" else "Normal",
			payload=row,
			idempotency_key=_notification_key(row, recipient),
		)
		return bool(result.get("created"))
	except Exception:
		if getattr(frappe, "log_error", None):
			frappe.log_error(
				title="Stock Expiry Internal Notification Failed",
				message=frappe.get_traceback() if getattr(frappe, "get_traceback", None) else "Stock expiry notification failed.",
			)
		return None


def _notification_key(row: dict, recipient: str) -> str:
	return "stock-expiry-status::{0}::{1}::{2}::{3}::{4}".format(
		recipient,
		row.get("item_code") or "",
		row.get("batch_no") or "",
		row.get("warehouse") or "",
		row.get("expiry_status") or "",
	)


def _log_external_channel_skipped(channel: str) -> None:
	if getattr(frappe, "log_error", None):
		frappe.log_error(
			title=f"Stock Expiry {channel} Notification Skipped",
			message=(
				f"{channel} stock expiry notifications are enabled, but provider routing is intentionally "
				"deferred to CoreEdge/ProcessEdge notification backends."
			),
		)


def _query_batch_stock_rows(filters) -> list[dict]:
	conditions = ["b.disabled = 0"]
	values = {}
	join_type = "LEFT JOIN" if cint(filters.get("include_zero_qty")) else "INNER JOIN"

	if filters.get("company"):
		conditions.append("w.company = %(company)s")
		values["company"] = filters.get("company")
	if filters.get("warehouse"):
		conditions.append("sle.warehouse = %(warehouse)s")
		values["warehouse"] = filters.get("warehouse")
	if filters.get("item_group"):
		conditions.append("i.item_group = %(item_group)s")
		values["item_group"] = filters.get("item_group")
	if filters.get("item"):
		conditions.append("b.item = %(item)s")
		values["item"] = filters.get("item")
	if filters.get("branch"):
		warehouse = get_branch_dispensary_warehouse(filters.get("branch"), filters.get("company"), required=False)
		if warehouse:
			conditions.append("sle.warehouse = %(branch_warehouse)s")
			values["branch_warehouse"] = warehouse

	having = "" if cint(filters.get("include_zero_qty")) else "HAVING qty > 0"
	sql = f"""
		SELECT
			b.item AS item_code,
			i.item_name,
			i.item_group,
			b.name AS batch_no,
			sle.warehouse,
			w.company,
			COALESCE(SUM(sle.actual_qty), 0) AS qty,
			i.stock_uom,
			b.expiry_date
		FROM `tabBatch` b
		{join_type} `tabStock Ledger Entry` sle
			ON sle.batch_no = b.name
			AND sle.item_code = b.item
			AND sle.is_cancelled = 0
		LEFT JOIN `tabWarehouse` w ON w.name = sle.warehouse
		LEFT JOIN `tabItem` i ON i.name = b.item
		WHERE {" AND ".join(conditions)}
		GROUP BY b.name, b.item, i.item_name, i.item_group, sle.warehouse, w.company, i.stock_uom, b.expiry_date
		{having}
		ORDER BY b.expiry_date ASC, b.item ASC, b.name ASC
	"""
	return frappe.db.sql(sql, values, as_dict=True)


def _has_stock_expiry_source() -> bool:
	try:
		return all(
			frappe.db.exists("DocType", doctype)
			for doctype in ("Batch", "Stock Ledger Entry", "Item", "Warehouse")
		)
	except Exception:
		return False


def _settings_bucket_value() -> str:
	return get_stock_expiry_monitor_settings().expiry_reminder_days


def _get_warehouse_branch_map(warehouses) -> dict[str, str]:
	warehouses = sorted({warehouse for warehouse in warehouses if warehouse})
	if not warehouses or not frappe.db.exists("DocType", "Branch"):
		return {}
	meta = frappe.get_meta("Branch")
	fields = ["name"]
	for fieldname in ("warehouse", "vetedge_dispensary_warehouse"):
		if meta.has_field(fieldname):
			fields.append(fieldname)
	if len(fields) == 1:
		return {}
	mapping_fields = fields[1:]
	rows = frappe.get_all(
		"Branch",
		fields=fields,
		or_filters={fieldname: ["in", warehouses] for fieldname in mapping_fields},
	)
	branch_map = {}
	for row in rows:
		for fieldname in mapping_fields:
			warehouse = row.get(fieldname)
			if warehouse in warehouses:
				branch_map[warehouse] = row.get("name")
	return branch_map


def _expiry_bucket_label(expiry_date, status: str, buckets: list[int], today=None) -> str:
	if status == "Expired":
		return _("Expired")
	if not expiry_date:
		return _("No Expiry Date")
	days = days_to_expiry(expiry_date, today=today)
	for bucket in buckets:
		if days is not None and days <= bucket:
			return _("Within {0} Days").format(bucket)
	return _("Beyond {0} Days").format(max(buckets, default=0))


def _expiry_sort_key(row: dict):
	days = row.get("days_to_expiry")
	return (days is None, days if days is not None else 999999, row.get("item_code") or "", row.get("batch_no") or "")


def _summary_card(label, value, indicator):
	return {"label": label, "value": value, "indicator": indicator, "datatype": "Int"}


def _col(fieldname, fieldtype="Data", options=None, label=None):
	column = {"fieldname": fieldname, "label": label or frappe.unscrub(fieldname), "fieldtype": fieldtype, "width": 160}
	if options:
		column["options"] = options
	return column
