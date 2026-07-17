# report_metadata.py
from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, cint

class HealthRule:
	def __init__(self, metric_key, scale=1.0, offset=0.0, max_score=100.0, formula_type="direct"):
		self.metric_key = metric_key
		self.scale = scale
		self.offset = offset
		self.max_score = max_score
		self.formula_type = formula_type  # "direct" or "inverse" (100 - value)

	def evaluate(self, metrics) -> float:
		val = flt(metrics.get(self.metric_key, 0.0))
		if self.formula_type == "inverse":
			score = 100.0 - (val * self.scale) + self.offset
		else:
			score = (val * self.scale) + self.offset
		return min(max(score, 0.0), self.max_score)


class RecommendationRule:
	def __init__(self, metric_key, operator, threshold_value, title, description, severity="warning"):
		self.metric_key = metric_key
		self.operator = operator  # "lt", "gt", "eq", "lte", "gte"
		self.threshold_value = flt(threshold_value)
		self.title = title
		self.description = description
		self.severity = severity

	def evaluate(self, metrics) -> bool:
		val = metrics.get(self.metric_key)
		if val is None:
			return False
		try:
			val_f = flt(val)
		except ValueError:
			return False

		if self.operator == "lt":
			return val_f < self.threshold_value
		elif self.operator == "gt":
			return val_f > self.threshold_value
		elif self.operator == "eq":
			return val_f == self.threshold_value
		elif self.operator == "lte":
			return val_f <= self.threshold_value
		elif self.operator == "gte":
			return val_f >= self.threshold_value
		return False


# Pluggable registry
_definitions = {}

def register_report(name: str, definition: dict):
	_definitions[name] = definition

def get_report_definition(name: str) -> dict | None:
	return _definitions.get(name)

def get_registered_reports() -> list[str]:
	return list(_definitions.keys())


# 1. Consultation Register Definition
register_report("Consultation Register", {
	"title": _("Consultation Report"),
	"icon": "stethoscope",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total", "title": _("Total Consultations"), "type": "count", "indicator": "Blue"},
		{"id": "completed", "title": _("Completed"), "type": "count", "field": "status", "value": {"Completed", "completed"}, "indicator": "Green"},
		{"id": "cancelled", "title": _("Cancelled"), "type": "count", "field": "status", "value": {"Cancelled", "cancelled", "Canceled", "canceled"}, "indicator": "Red"},
		{"id": "pending", "title": _("Pending"), "type": "count", "field": "status", "value": {"Active", "active", "In Progress", "in progress", "Open", "open", "Draft", "draft", "Ready for Treatment", "ready for treatment"}, "indicator": "Orange"},
		{"id": "completion_rate", "title": _("Completion Rate"), "type": "percentage", "numerator": "completed", "denominator": "total", "indicator": "Green", "datatype": "Percent"},
		{"id": "avg_duration", "title": _("Average Duration"), "type": "average", "field": "duration_minutes", "indicator": "Blue", "datatype": "Float", "suffix": " mins"},
		{"id": "avg_revenue", "title": _("Average Revenue"), "type": "average", "field": "planned_treatment_total", "indicator": "Purple", "datatype": "Currency"}
	],
	"health_rules": HealthRule(metric_key="completion_rate"),
	"recommendation_rules": [
		RecommendationRule(
			metric_key="completion_rate",
			operator="lt",
			threshold_value=85.0,
			title=_("Low Consultation Completion Rate"),
			description=_("Consider reviewing clinical workflow delays and nurse-to-doctor handoff procedures."),
			severity="warning"
		),
		RecommendationRule(
			metric_key="cancelled",
			operator="gt",
			threshold_value=5,
			title=_("High Cancellations Detected"),
			description=_("Review cancellation patterns, doctor availability times, or consider deposit booking rules."),
			severity="danger"
		)
	],
	"empty_state": {
		"message": _("No consultations were completed during this period."),
		"suggestions": [
			_("Ensure you selected the correct service branch or practitioner filter."),
			_("Verify if clinical check-in staff are actively logging consultation records."),
			_("Check if appointments were properly converted to clinical consultations.")
		]
	}
})

# 2. Lab Order Report Definition
register_report("Lab Order Report", {
	"title": _("Laboratory Report"),
	"icon": "flask",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total", "title": _("Tests Performed"), "type": "count", "indicator": "Blue"},
		{"id": "pending", "title": _("Pending Collection"), "type": "count", "field": "status", "value": {"Pending", "pending", "Requested", "requested", "Open", "open", "Draft", "draft", "Pending Collection", "pending collection"}, "indicator": "Orange"},
		{"id": "cancelled", "title": _("Cancelled"), "type": "count", "field": "status", "value": {"Cancelled", "cancelled", "Canceled", "canceled"}, "indicator": "Red"},
		{"id": "completed", "title": _("Completed"), "type": "count", "field": "status", "value": {"Completed", "completed", "Reviewed", "reviewed"}, "indicator": "Green"},
		{"id": "avg_turnaround", "title": _("Average Turnaround"), "type": "average_duration", "start_field": "requested_on", "end_field": "result_entered_on", "unit": "hours", "indicator": "Blue", "datatype": "Float", "suffix": " hrs"},
		{"id": "unbilled", "title": _("Unbilled / Unpaid Labs"), "type": "count_missing_field", "field": "linked_invoice", "indicator": "Orange"}
	],
	"health_rules": HealthRule(metric_key="pending", formula_type="inverse", scale=5.0), # 100 - (pending * 5)
	"recommendation_rules": [
		RecommendationRule(
			metric_key="pending",
			operator="gt",
			threshold_value=10,
			title=_("Pending Lab Test Backlog"),
			description=_("Liaise with laboratory staff to expedite processing of sample collections and enter pending results."),
			severity="warning"
		)
	],
	"empty_state": {
		"message": _("No laboratory test orders were found matching these filters."),
		"suggestions": [
			_("Ensure you selected the correct branch and requesting doctor."),
			_("Verify if the laboratory device integration or callback webhooks are operating correctly.")
		]
	}
})

# 3. Vaccination Report Definition
register_report("Vaccination Report", {
	"title": _("Vaccination Report"),
	"icon": "shield-check",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total", "title": _("Vaccinations Scheduled"), "type": "count", "indicator": "Blue"},
		{"id": "administered", "title": _("Administered"), "type": "count", "field": "status", "value": {"Administered", "administered", "Completed", "completed"}, "indicator": "Green"},
		{"id": "due_soon", "title": _("Due Soon"), "type": "count", "field": "due_status", "value": {"Due Soon", "due soon"}, "indicator": "Orange"},
		{"id": "overdue", "title": _("Overdue"), "type": "count", "field": "due_status", "value": {"Overdue", "overdue"}, "indicator": "Red"},
		{"id": "compliance_rate", "title": _("Compliance Rate"), "type": "percentage", "numerator": "administered", "denominator": "total", "indicator": "Green", "datatype": "Percent"}
	],
	"health_rules": HealthRule(metric_key="compliance_rate"),
	"recommendation_rules": [
		RecommendationRule(
			metric_key="compliance_rate",
			operator="lt",
			threshold_value=80.0,
			title=_("Vaccination Compliance Fell"),
			description=_("Review appointment reminders and client contact lists to reduce missed vaccination dosages."),
			severity="warning"
		),
		RecommendationRule(
			metric_key="overdue",
			operator="gt",
			threshold_value=10,
			title=_("High Overdue Patient Count"),
			description=_("Run the missed vaccination notifications event queue to alert pet owners."),
			severity="danger"
		)
	],
	"empty_state": {
		"message": _("No patient vaccination events found during this window."),
		"suggestions": [
			_("Check default patient registers or branch defaults."),
			_("Ensure that patient vaccine products are correctly set up and active in the item catalog.")
		]
	}
})

# 4. Active Hospitalisations Definition
register_report("Active Hospitalisations", {
	"title": _("Hospitalisation Report"),
	"icon": "bed",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": False,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total", "title": _("Active Admissions"), "type": "count", "indicator": "Blue"},
		{"id": "critical", "title": _("Critical Care Admissions"), "type": "count", "field": "care_level", "value": {"Critical", "critical", "High", "high", "High Care", "high care", "Intensive", "intensive"}, "indicator": "Red"},
		{"id": "avg_stay", "title": _("Average Stay Duration"), "type": "average", "field": "days_admitted", "indicator": "Blue", "datatype": "Float", "suffix": " days"},
		{"id": "unbilled", "title": _("Unbilled Admission Charges"), "type": "sum", "field": "pending_charges", "indicator": "Orange", "datatype": "Currency"}
	],
	"health_rules": HealthRule(metric_key="critical", formula_type="inverse", scale=25.0), # 100 - (critical * 25)
	"recommendation_rules": [
		RecommendationRule(
			metric_key="critical",
			operator="gt",
			threshold_value=3,
			title=_("High Volume of Critical Cases"),
			description=_("Ensure intensive care nursing shifts are fully scheduled and emergency drug stock is validated."),
			severity="danger"
		)
	],
	"empty_state": {
		"message": _("No active hospitalisation stays found."),
		"suggestions": [
			_("Admit a patient from a veterinary consultation page first."),
			_("Verify care ward capacity settings or active location availability.")
		]
	}
})

# 5. Boarding Report Definition
register_report("Boarding Report", {
	"title": _("Boarding Report"),
	"icon": "home",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total", "title": _("Active Stays"), "type": "count", "field": "status", "value": {"Active", "active", "Checked In", "checked in", "Admitted", "admitted", "In House", "in house"}, "indicator": "Green"},
		{"id": "upcoming", "title": _("Upcoming Bookings"), "type": "count", "field": "status", "value": {"Booked", "booked", "Scheduled", "scheduled", "Confirmed", "confirmed", "Reserved", "reserved"}, "indicator": "Blue"},
		{"id": "avg_stay", "title": _("Average Boarding Stay"), "type": "average", "field": "stay_days", "indicator": "Blue", "datatype": "Float", "suffix": " days"},
		{"id": "revenue", "title": _("Boarding Revenue"), "type": "sum", "field": "total_boarding_charge", "indicator": "Purple", "datatype": "Currency"},
		{"id": "unbilled", "title": _("Unbilled Boarding"), "type": "count_missing_field", "field": "linked_invoice", "indicator": "Orange"}
	],
	"health_rules": HealthRule(metric_key="unbilled", formula_type="inverse", scale=20.0),
	"recommendation_rules": [
		RecommendationRule(
			metric_key="unbilled",
			operator="gt",
			threshold_value=3,
			title=_("Unbilled Boarding Bookings"),
			description=_("Draft Sales Invoices for checked-out pets to finalize and close stays."),
			severity="warning"
		)
	],
	"empty_state": {
		"message": _("No boarding kennel reservations found in this period."),
		"suggestions": [
			_("Create a boarding reservation for standard stays."),
			_("Verify kennel ward mapping and status parameters.")
		]
	}
})

# 6. Grooming Report Definition
register_report("Grooming Report", {
	"title": _("Grooming Report"),
	"icon": "scissors",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total", "title": _("Total Sessions"), "type": "count", "indicator": "Blue"},
		{"id": "completed", "title": _("Completed"), "type": "count", "field": "status", "value": {"Completed", "completed"}, "indicator": "Green"},
		{"id": "revenue", "title": _("Grooming Revenue"), "type": "sum", "field": "total_charge", "indicator": "Purple", "datatype": "Currency"},
		{"id": "unpaid", "title": _("Unpaid Grooming"), "type": "count_missing_field", "field": "linked_invoice", "indicator": "Orange"},
		{"id": "popular", "title": _("Popular Service"), "type": "mode", "field": "grooming_service", "indicator": "Purple"}
	],
	"health_rules": HealthRule(metric_key="unpaid", formula_type="inverse", scale=20.0),
	"recommendation_rules": [
		RecommendationRule(
			metric_key="unpaid",
			operator="gt",
			threshold_value=3,
			title=_("Unpaid Grooming Sessions"),
			description=_("Follow up with customers to process pending invoices for completed sessions."),
			severity="warning"
		)
	],
	"empty_state": {
		"message": _("No grooming sessions matched your filter parameters."),
		"suggestions": [
			_("Confirm scheduler time slots for grooming staff."),
			_("Verify species/breed requirements are set up correctly.")
		]
	}
})

# 7. Dispensary Activity Report Definition
register_report("Dispensary Activity Report", {
	"title": _("Dispensary Report"),
	"icon": "clipboard",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total", "title": _("Prescriptions Filed"), "type": "count", "indicator": "Blue"},
		{"id": "dispensed", "title": _("Dispensed Prescriptions"), "type": "count", "field": "status", "value": {"Dispensed", "dispensed"}, "indicator": "Green"},
		{"id": "revenue", "title": _("Dispensary Revenue"), "type": "sum", "field": "total_amount", "indicator": "Purple", "datatype": "Currency"},
		{"id": "expiring", "title": _("Expiring Soon Batches"), "type": "count", "field": "expiry_status", "value": {"expiring soon", "expired"}, "indicator": "Red"},
		{"id": "low_stock", "title": _("Low Stock Items"), "type": "count", "field": "stock_status", "value": {"low stock"}, "indicator": "Orange"}
	],
	"health_rules": HealthRule(metric_key="low_stock", formula_type="inverse", scale=10.0),
	"recommendation_rules": [
		RecommendationRule(
			metric_key="expiring",
			operator="gt",
			threshold_value=0,
			title=_("Expiring Dispensary Batches Found"),
			description=_("Liaise with pharmacy staff to quarantine expiring items and reorder active compounds."),
			severity="danger"
		),
		RecommendationRule(
			metric_key="low_stock",
			operator="gt",
			threshold_value=5,
			title=_("Critical Low Stock Items"),
			description=_("Initiate purchase orders for core stock items falling below safety margins."),
			severity="warning"
		)
	],
	"empty_state": {
		"message": _("No pharmacy or dispensary activity records logged in this period."),
		"suggestions": [
			_("Ensure clinical prescriptions are linked to active inventory warehouses."),
			_("Check stock levels in the VetEdge Item catalog.")
		]
	}
})

# 8. Financial / Revenue Summary Definition
register_report("Revenue Summary", {
	"title": _("Revenue Report"),
	"icon": "credit-card",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "total_billed", "title": _("Total Billed"), "type": "sum", "field": "grand_total", "indicator": "Blue", "datatype": "Currency"},
		{"id": "total_paid", "title": _("Total Paid"), "type": "sum", "field": "paid_amount", "indicator": "Green", "datatype": "Currency"},
		{"id": "outstanding", "title": _("Outstanding"), "type": "sum", "field": "outstanding_amount", "indicator": "Orange", "datatype": "Currency"},
		{"id": "draft", "title": _("Draft Invoices"), "type": "count", "field": "status", "value": {"Draft", "draft"}, "indicator": "Gray"},
		{"id": "collection_rate", "title": _("Collection Rate"), "type": "percentage", "numerator": "total_paid", "denominator": "total_billed", "indicator": "Green", "datatype": "Percent"}
	],
	"health_rules": HealthRule(metric_key="collection_rate"),
	"recommendation_rules": [
		RecommendationRule(
			metric_key="collection_rate",
			operator="lt",
			threshold_value=80.0,
			title=_("Collection Rate Fell Below Target"),
			description=_("Follow up with outstanding customer accounts and prioritize processing payment runs."),
			severity="warning"
		),
		RecommendationRule(
			metric_key="outstanding",
			operator="gt",
			threshold_value=50000.0,
			title=_("High Outstanding Balance"),
			description=_("Review older accounts receivable entries and enforce credit policies."),
			severity="danger"
		)
	],
	"empty_state": {
		"message": _("No billing invoices logged in this period."),
		"suggestions": [
			_("Ensure consultations or dispensary actions are finalized to trigger billing."),
			_("Verify ERPNext Sales Invoice connection settings.")
		]
	}
})

# 9. Unpaid Invoice Report Definition
register_report("Unpaid Invoice Report", {
	"title": _("Aged Accounts Report"),
	"icon": "clock",
	"capabilities": {
		"supports_date_presets": True,
		"supports_comparison": True,
		"supports_health_score": True,
		"supports_recommendations": True,
		"supports_drilldown": True,
		"supports_export": True
	},
	"cards": [
		{"id": "outstanding", "title": _("Outstanding Balance"), "type": "sum", "field": "outstanding_amount", "indicator": "Orange", "datatype": "Currency"},
		{"id": "total_unpaid", "title": _("Unpaid Invoices"), "type": "count", "indicator": "Orange"},
		{"id": "avg_outstanding", "title": _("Average Outstanding"), "type": "average", "field": "outstanding_amount", "indicator": "Blue", "datatype": "Currency"},
		{"id": "aged_30", "title": _("30+ Days Overdue"), "type": "count_comparison", "field": "age_days", "op": ">=", "value": 30, "indicator": "Orange"},
		{"id": "aged_60", "title": _("60+ Days Overdue"), "type": "count_comparison", "field": "age_days", "op": ">=", "value": 60, "indicator": "Red"}
	],
	"health_rules": HealthRule(metric_key="aged_60", formula_type="inverse", scale=10.0),
	"recommendation_rules": [
		RecommendationRule(
			metric_key="aged_60",
			operator="gt",
			threshold_value=0,
			title=_("Severe Overdue Accounts Detected"),
			description=_("Send warning communications to clients with invoices unpaid for more than 60 days."),
			severity="danger"
		)
	],
	"empty_state": {
		"message": _("No unpaid invoices outstanding."),
		"suggestions": [
			_("Awesome! All practice bills for this period are fully paid."),
			_("Check filter statuses to include historically paid accounts.")
		]
	}
})
