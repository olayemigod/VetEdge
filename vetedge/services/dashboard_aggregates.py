from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.consultation_report import _filters, _query_filters, _where_clause


def get_consultation_dashboard_aggregates(filters=None) -> dict:
	"""Return dashboard-ready consultation aggregates without detail-row materialization."""
	report_filters = _filters(filters)
	query_filters = _query_filters(report_filters)
	where_sql, params = _where_clause(query_filters, report_filters)

	total_rows = frappe.db.sql(
		f"SELECT COUNT(*) AS `row_count` FROM `tabVeterinary Consultation` c WHERE {where_sql}",
		params,
		as_dict=True,
	)
	total = cint(total_rows[0].get("row_count")) if total_rows else 0

	by_day = frappe.db.sql(
		f"""
		SELECT DATE(c.`consultation_datetime`) AS `label`, COUNT(*) AS `value`
		FROM `tabVeterinary Consultation` c
		WHERE {where_sql}
		GROUP BY DATE(c.`consultation_datetime`)
		ORDER BY DATE(c.`consultation_datetime`) ASC
		""",
		params,
		as_dict=True,
	)
	by_branch = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(c.`service_branch`, ''), %(unassigned)s) AS `label`, COUNT(*) AS `value`
		FROM `tabVeterinary Consultation` c
		WHERE {where_sql}
		GROUP BY c.`service_branch`
		ORDER BY `value` DESC, `label` ASC
		""",
		{**params, "unassigned": cstr(_("Unassigned"))},
		as_dict=True,
	)
	by_type = frappe.db.sql(
		f"""
		SELECT COALESCE(NULLIF(c.`consultation_type`, ''), %(unspecified)s) AS `label`, COUNT(*) AS `value`
		FROM `tabVeterinary Consultation` c
		WHERE {where_sql}
		GROUP BY c.`consultation_type`
		ORDER BY `value` DESC, `label` ASC
		""",
		{**params, "unspecified": cstr(_("Unspecified"))},
		as_dict=True,
	)

	return {
		"total": total,
		"by_day": _series(by_day),
		"by_branch": _series(by_branch),
		"by_type": _series(by_type),
		"metadata": {
			"mode": "database_aggregate",
			"detail_rows_materialized": False,
		},
	}


def _series(rows) -> list[dict]:
	return [
		{"label": cstr(row.get("label")), "value": cint(row.get("value"))}
		for row in rows or []
		if row.get("label") not in (None, "")
	]
