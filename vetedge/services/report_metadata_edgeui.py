from __future__ import annotations

from frappe import _

from vetedge.services.report_metadata import register_report


def register_edgeui_report_definitions() -> None:
	"""Register the first EdgeSuite report migration definitions.

	These definitions only describe reporting cards and empty states. They do not
	change report queries, permissions, source documents, or accounting records.
	"""
	register_report(
		"Branch Performance Report",
		{
			"title": _("Branch Performance"),
			"icon": "building",
			"capabilities": {
				"supports_date_presets": True,
				"supports_comparison": True,
				"supports_health_score": False,
				"supports_recommendations": False,
				"supports_drilldown": False,
				"supports_export": True,
			},
			"cards": [
				{
					"id": "branches",
					"title": _("Branches"),
					"type": "count",
					"indicator": "Blue",
				},
				{
					"id": "consultations",
					"title": _("Consultations"),
					"type": "sum",
					"field": "consultation_count",
					"indicator": "Blue",
				},
				{
					"id": "appointments",
					"title": _("Appointments"),
					"type": "sum",
					"field": "appointment_count",
					"indicator": "Blue",
				},
				{
					"id": "revenue",
					"title": _("Revenue"),
					"type": "sum",
					"field": "revenue_total",
					"indicator": "Green",
					"datatype": "Currency",
				},
				{
					"id": "outstanding",
					"title": _("Outstanding"),
					"type": "sum",
					"field": "outstanding_total",
					"indicator": "Orange",
					"datatype": "Currency",
				},
				{
					"id": "laboratory_orders",
					"title": _("Laboratory Orders"),
					"type": "sum",
					"field": "lab_order_count",
					"indicator": "Purple",
				},
				{
					"id": "vaccinations",
					"title": _("Vaccinations"),
					"type": "sum",
					"field": "vaccination_count",
					"indicator": "Green",
				},
			],
			"empty_state": {
				"message": _("No branch activity matched the selected filters."),
				"suggestions": [
					_("Choose another date range or branch."),
					_("Confirm that consultations, appointments, and submitted invoices carry the correct branch."),
				],
			},
		},
	)

	register_report(
		"Planned Treatment",
		{
			"title": _("Planned Treatment"),
			"icon": "stethoscope",
			"capabilities": {
				"supports_date_presets": True,
				"supports_comparison": True,
				"supports_health_score": False,
				"supports_recommendations": False,
				"supports_drilldown": False,
				"supports_export": True,
			},
			"cards": [
				{
					"id": "planned_lines",
					"title": _("Planned Lines"),
					"type": "count",
					"indicator": "Blue",
				},
				{
					"id": "planned_value",
					"title": _("Planned Value"),
					"type": "sum",
					"field": "amount",
					"indicator": "Green",
					"datatype": "Currency",
				},
				{
					"id": "average_line_value",
					"title": _("Average Line Value"),
					"type": "average",
					"field": "amount",
					"indicator": "Purple",
					"datatype": "Currency",
				},
				{
					"id": "pending",
					"title": _("Pending / Active"),
					"type": "count",
					"field": "status",
					"value": {
						"Draft",
						"In Progress",
						"Awaiting Payment",
						"Pending Dispensary",
						"Ready for Treatment",
					},
					"indicator": "Orange",
				},
				{
					"id": "completed",
					"title": _("Completed"),
					"type": "count",
					"field": "status",
					"value": {"Completed"},
					"indicator": "Green",
				},
			],
			"empty_state": {
				"message": _("No planned treatment items matched the selected filters."),
				"suggestions": [
					_("Choose another date range, branch, patient, practitioner, or item."),
					_("Confirm that treatment items were added to the consultation Treatment Plan."),
				],
			},
		},
	)
