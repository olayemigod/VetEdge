from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services import consultation_report
from vetedge.services.portal_access import require_internal_user
from vetedge.services.reporting_capabilities import require_reporting_action
from vetedge.services.reporting_entitlement_adapter import check_advanced_reporting_entitlement
from vetedge.services.reporting_structure import _get_user_full_name_map

SUPPORTED_REPORT = "Consultation Register"
MAX_GROUPS = 50
GROUP_DIMENSIONS = {
	"branch": {"field": "service_branch", "label": "Branch"},
	"practitioner": {"field": "consulting_practitioner", "label": "Practitioner"},
	"consultation_type": {"field": "consultation_type", "label": "Consultation Type"},
	"status": {"field": "status", "label": "Status"},
}


def _parse_filters(value) -> dict:
	if not value:
		return {}
	parsed = value if isinstance(value, dict) else frappe.parse_json(value)
	if not isinstance(parsed, dict):
		frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
	return {str(key): item for key, item in parsed.items() if item not in (None, "")}


def _require_advanced_grouping() -> None:
	entitlement = check_advanced_reporting_entitlement()
	if entitlement.get("allowed"):
		return
	frappe.throw(
		_("Grouping and subtotals are an Advanced reporting feature and are not included in the current Plan."),
		frappe.PermissionError,
	)


def _group_rows(where_sql: str, params: dict, dimension: str) -> list[dict]:
	definition = GROUP_DIMENSIONS[dimension]
	field = definition["field"]
	planned_treatment_available = frappe.db.exists("DocType", "Planned Treatment Item")
	planned_join = ""
	planned_expression = "0"
	row_count_expression = "COUNT(*)"
	completed_expression = "SUM(CASE WHEN c.`status` = 'Completed' THEN 1 ELSE 0 END)"
	if planned_treatment_available:
		planned_join = """
			LEFT JOIN `tabPlanned Treatment Item` pt
				ON pt.`parent` = c.`name`
				AND pt.`parenttype` = 'Veterinary Consultation'
		"""
		planned_expression = """
			SUM(
				CASE
					WHEN pt.`name` IS NULL THEN 0
					WHEN IFNULL(pt.`amount`, 0) != 0 THEN pt.`amount`
					ELSE IFNULL(pt.`qty`, 0) * IFNULL(pt.`rate`, 0)
				END
			)
		"""
		row_count_expression = "COUNT(DISTINCT c.`name`)"
		completed_expression = "COUNT(DISTINCT CASE WHEN c.`status` = 'Completed' THEN c.`name` END)"

	query_params = dict(params)
	query_params["limit"] = MAX_GROUPS
	return frappe.db.sql(
		f"""
		SELECT
			IFNULL(c.`{field}`, '') AS `group_key`,
			{row_count_expression} AS `row_count`,
			{completed_expression} AS `completed`,
			{planned_expression} AS `planned_value`
		FROM `tabVeterinary Consultation` c
		{planned_join}
		WHERE {where_sql}
		GROUP BY c.`{field}`
		ORDER BY `row_count` DESC, `group_key` ASC
		LIMIT %(limit)s
		""",
		query_params,
		as_dict=True,
	)


def _label_rows(rows: list[dict], dimension: str) -> list[dict]:
	practitioner_names = {}
	if dimension == "practitioner":
		practitioner_names = _get_user_full_name_map(row.get("group_key") for row in rows)

	result = []
	for row in rows:
		group_key = cstr(row.get("group_key") or "").strip()
		row_count = cint(row.get("row_count"))
		completed = cint(row.get("completed"))
		planned_value = flt(row.get("planned_value"))
		label = practitioner_names.get(group_key) if dimension == "practitioner" else group_key
		result.append(
			{
				"key": group_key or "__unspecified__",
				"group_key": group_key,
				"label": label or _("Unspecified"),
				"row_count": row_count,
				"completed": completed,
				"completion_rate": flt((completed / row_count) * 100, 1) if row_count else 0,
				"planned_value": planned_value,
				"average_planned_value": flt(planned_value / row_count, 2) if row_count else 0,
			}
		)
	return result


@frappe.whitelist()
@frappe.read_only()
def get_report_grouping(report_name: str, dimension: str, filters=None) -> dict:
	require_internal_user()
	report_name = cstr(report_name or "").strip()
	dimension = cstr(dimension or "").strip()
	if report_name != SUPPORTED_REPORT:
		frappe.throw(_("Grouping is not available for this report yet."), frappe.ValidationError)
	if dimension not in GROUP_DIMENSIONS:
		frappe.throw(_("Unsupported grouping dimension."), frappe.ValidationError)

	require_reporting_action(report_name, "report", "view")
	_require_advanced_grouping()
	consultation_report._require_read_permission()

	report_filters = consultation_report._filters(_parse_filters(filters))
	query_filters = consultation_report._query_filters(report_filters)
	where_sql, params = consultation_report._where_clause(query_filters, report_filters)
	rows = _label_rows(_group_rows(where_sql, params, dimension), dimension)
	definition = GROUP_DIMENSIONS[dimension]

	return {
		"title": _("Grouped Consultation Summary"),
		"dimension": dimension,
		"group_label": _(definition["label"]),
		"rows": rows,
		"measures": [
			{"key": "row_count", "label": _("Consultations"), "datatype": "Int"},
			{"key": "completed", "label": _("Completed"), "datatype": "Int"},
			{"key": "completion_rate", "label": _("Completion Rate"), "datatype": "Percent"},
			{"key": "planned_value", "label": _("Planned Value"), "datatype": "Currency"},
			{"key": "average_planned_value", "label": _("Average Planned Value"), "datatype": "Currency"},
		],
		"metadata": {
			"aggregate_only": True,
			"detail_rows_materialized": False,
			"group_limit": MAX_GROUPS,
			"source": "consultation-register",
			"planned_value_mode": "filtered_child_join",
		},
	}
