from __future__ import annotations

from vetedge.services.scheduled_report_bridge import get_scheduled_report_data


def execute(filters=None):
	filters = filters or {}
	return get_scheduled_report_data(
		report_name=filters.get("target_report"),
		filters=filters.get("target_filters"),
		selected_columns=filters.get("selected_columns"),
		row_limit=filters.get("row_limit") or 500,
	)
