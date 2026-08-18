from __future__ import annotations

import frappe
from frappe.utils import add_days, cint, flt, getdate, nowdate

from vetedge.services.stock import get_branch_dispensary_warehouse
from vetedge.services.stock_expiry_monitor import (
	_expiry_bucket_label,
	_get_warehouse_branch_map,
	_has_stock_expiry_source,
	_settings_bucket_value,
	parse_expiry_buckets,
)

MAX_INTERACTIVE_PAGE_LENGTH = 500
DEFAULT_INTERACTIVE_PAGE_LENGTH = 50


def get_stock_expiry_interactive_data(
	filters=None,
	*,
	expiry_window: str = "all",
	limit: int = DEFAULT_INTERACTIVE_PAGE_LENGTH,
	offset: int = 0,
) -> dict:
	"""Return summary plus one database-paginated Stock Expiry window.

	This path is intentionally separate from get_stock_expiry_rows(), which
	remains the full-dataset contract used by reports and notification jobs.
	"""
	filters = frappe._dict(filters or {})
	limit = min(max(cint(limit) or DEFAULT_INTERACTIVE_PAGE_LENGTH, 1), MAX_INTERACTIVE_PAGE_LENGTH)
	offset = max(cint(offset), 0)

	if not _has_stock_expiry_source():
		return {
			"summary": _empty_summary(),
			"rows": [],
			"total_count": 0,
			"limit": limit,
			"offset": offset,
		}

	buckets = parse_expiry_buckets(filters.get("expiry_buckets") or _settings_bucket_value())
	today = getdate(filters.get("posting_date") or nowdate())
	max_days = max(buckets, default=0)
	expiring_soon_date = add_days(today, max_days) if max_days else today

	source_sql, values = _build_batch_stock_source(filters)
	values.update(
		{
			"today": today,
			"max_days": max_days,
			"expiring_soon_date": expiring_soon_date,
			"limit": limit,
			"offset": offset,
		}
	)
	classified_sql = _classified_source_sql(source_sql)

	summary_rows = frappe.db.sql(
		f"""
		SELECT
			COUNT(*) AS total_items,
			COALESCE(SUM(CASE WHEN expiry_status = 'Expired' THEN 1 ELSE 0 END), 0) AS expired_items,
			COALESCE(SUM(CASE WHEN expiry_status = 'Expiring Soon' THEN 1 ELSE 0 END), 0) AS expiring_soon,
			COALESCE(SUM(CASE WHEN expiry_status = 'Safe' THEN 1 ELSE 0 END), 0) AS safe_items,
			COALESCE(
				SUM(
					CASE
						WHEN expiry_status IN ('Expired', 'Expiring Soon') THEN qty
						ELSE 0
					END
				),
				0
			) AS affected_qty,
			COUNT(
				DISTINCT CASE
					WHEN expiry_status IN ('Expired', 'Expiring Soon') THEN warehouse
					ELSE NULL
				END
			) AS affected_warehouses,
			COUNT(
				DISTINCT CASE
					WHEN expiry_status = 'Expired' THEN item_code
					ELSE NULL
				END
			) AS highest_risk_items
		FROM ({classified_sql}) classified
		""",
		values,
		as_dict=True,
	)
	summary = dict(summary_rows[0]) if summary_rows else _empty_summary()
	for key in ("total_items", "expired_items", "expiring_soon", "safe_items", "affected_warehouses", "highest_risk_items"):
		summary[key] = cint(summary.get(key))
	summary["affected_qty"] = flt(summary.get("affected_qty"))

	window_condition = _window_condition(expiry_window)
	rows = frappe.db.sql(
		f"""
		SELECT
			item_code,
			item_name,
			item_group,
			batch_no,
			warehouse,
			company,
			qty,
			stock_uom,
			expiry_date,
			DATEDIFF(expiry_date, %(today)s) AS days_to_expiry,
			expiry_status,
			COUNT(*) OVER() AS total_count
		FROM ({classified_sql}) classified
		{window_condition}
		ORDER BY
			CASE WHEN expiry_date IS NULL THEN 1 ELSE 0 END ASC,
			expiry_date ASC,
			item_code ASC,
			batch_no ASC
		LIMIT %(limit)s OFFSET %(offset)s
		""",
		values,
		as_dict=True,
	)
	total_count = cint(rows[0].get("total_count")) if rows else 0
	if not rows and offset:
		count_rows = frappe.db.sql(
			f"""
			SELECT COUNT(*) AS total_count
			FROM ({classified_sql}) classified
			{window_condition}
			""",
			values,
			as_dict=True,
		)
		total_count = cint(count_rows[0].get("total_count")) if count_rows else 0

	branch_map = _get_warehouse_branch_map(row.get("warehouse") for row in rows)
	result_rows = []
	for row in rows:
		row = dict(row)
		row.pop("total_count", None)
		row["qty"] = flt(row.get("qty"))
		row["branch"] = branch_map.get(row.get("warehouse"))
		row["expiry_bucket"] = _expiry_bucket_label(
			row.get("expiry_date"),
			row.get("expiry_status"),
			buckets,
			today=today,
		)
		result_rows.append(row)

	return {
		"summary": summary,
		"rows": result_rows,
		"total_count": total_count,
		"limit": limit,
		"offset": offset,
	}


def _build_batch_stock_source(filters) -> tuple[str, dict]:
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
		warehouse = get_branch_dispensary_warehouse(
			filters.get("branch"),
			filters.get("company"),
			required=False,
		)
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
		GROUP BY
			b.name,
			b.item,
			i.item_name,
			i.item_group,
			sle.warehouse,
			w.company,
			i.stock_uom,
			b.expiry_date
		{having}
	"""
	return sql, values


def _classified_source_sql(source_sql: str) -> str:
	return f"""
		SELECT
			source_rows.*,
			CASE
				WHEN source_rows.expiry_date IS NOT NULL
					AND source_rows.expiry_date <= %(today)s
					THEN 'Expired'
				WHEN %(max_days)s > 0
					AND source_rows.expiry_date IS NOT NULL
					AND source_rows.expiry_date <= %(expiring_soon_date)s
					THEN 'Expiring Soon'
				ELSE 'Safe'
			END AS expiry_status
		FROM ({source_sql}) source_rows
	"""


def _window_condition(expiry_window: str) -> str:
	window = str(expiry_window or "all").strip().lower()
	if window == "expired":
		return "WHERE expiry_status = 'Expired'"
	if window == "expiring soon":
		return "WHERE expiry_status = 'Expiring Soon'"
	return ""


def _empty_summary() -> dict:
	return {
		"total_items": 0,
		"expired_items": 0,
		"expiring_soon": 0,
		"safe_items": 0,
		"affected_qty": 0.0,
		"affected_warehouses": 0,
		"highest_risk_items": 0,
	}
