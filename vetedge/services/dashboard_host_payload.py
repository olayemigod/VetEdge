from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cstr, flt

from vetedge.services import reporting_logic_v4 as v4
from vetedge.services import reporting_logic_v5 as v5
from vetedge.services.executive_financial_metrics import count_executive_unpaid_invoices
from vetedge.services.report_visibility import normalize_dashboard_filters, validate_dashboard_access


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
	"""Shared-dashboard adapter with an optimized Executive unpaid KPI path."""
	key = cstr(dashboard_key or "").strip()
	if key != "executive":
		return v5.get_dashboard_payload(key, filters)

	validate_dashboard_access(key)
	normalized = normalize_dashboard_filters(key, v4._to_dict(filters))
	return _executive_payload(normalized)


def _executive_payload(filters) -> dict:
	"""Preserve reporting_logic_v5 Executive semantics without full unpaid report rows."""
	consultation_rows = v4._rows("Consultation Register", filters)
	revenue_rows = v4._rows("Revenue Summary", filters)
	unpaid_count = count_executive_unpaid_invoices(filters)

	payload = v5._base_payload("executive", _("Executive Dashboard"))
	payload["kpis"] = [
		v4._kpi(_("Consultations in Range"), len(consultation_rows)),
		v4._kpi(_("Revenue in Range"), v4._currency(sum(flt(row.get("grand_total")) for row in revenue_rows))),
		v4._kpi(_("Unpaid Invoices in Range"), unpaid_count),
		v4._kpi(_("Appointments in Range"), v5._appointments_in_range(filters)),
		v4._kpi(_("Active Patients (Current)"), v4._active_patients(filters)),
	]
	payload["charts"] = []
	if v4._is_multi_day_range(filters):
		payload["charts"].append(v5._consultation_chart(consultation_rows))
	payload["charts"].extend(
		[
			v4._consultation_by_branch_chart(consultation_rows),
			v4._consultation_type_chart(consultation_rows),
			v4._daily_revenue_chart(revenue_rows),
			v4._branch_revenue_chart(revenue_rows),
		]
	)
	payload["filter_scope"] = {
		"from_date": filters.get("from_date"),
		"to_date": filters.get("to_date"),
		"branch": filters.get("branch"),
		"message": _("KPI cards and charts use the same selected date range. Active Patients is a current-state snapshot."),
	}
	return payload
