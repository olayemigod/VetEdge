import unittest
from unittest.mock import patch

import frappe

frappe._ = lambda value, *args, **kwargs: value

from vetedge.services import report_insights
from vetedge.services import reporting_logic_v3


def summary_value(summary, label):
	for row in summary:
		if row.get("label") == label:
			return row.get("value")
	raise AssertionError(f"Missing summary card: {label}")


class TestReportInsights(unittest.TestCase):
	def test_insight_card_formatting(self):
		card = report_insights.insight_card("Total Billed", 1250, "Green", "Currency", "Filtered period")
		self.assertEqual(card["label"], "Total Billed")
		self.assertEqual(card["value"], 1250)
		self.assertEqual(card["indicator"], "Green")
		self.assertEqual(card["datatype"], "Currency")
		self.assertEqual(card["subtitle"], "Filtered period")

	def test_percent_is_zero_when_denominator_is_zero(self):
		self.assertEqual(report_insights.percent(4, 0), 0)

	def test_structured_report_summary_uses_filtered_rows_from_base_report(self):
		rows = [
			{"service_branch": "Main", "status": "Completed", "payment_status": "Paid", "planned_treatment_total": 100},
			{"service_branch": "Annex", "status": "Completed", "payment_status": "Paid", "planned_treatment_total": 200},
			{"service_branch": "Main", "status": "In Progress", "payment_status": "Unpaid", "planned_treatment_total": 0},
		]
		with (
			patch("vetedge.services.reporting_logic_v3.normalize_report_filters", side_effect=lambda report, filters: filters),
			patch("vetedge.services.reporting_logic_v3._base_execute_structured_report", return_value=([], rows, None, None, [])),
		):
			_, data, _, _, summary = reporting_logic_v3.execute_structured_report(
				"Consultation Register",
				{"from_date": "2026-07-01", "to_date": "2026-07-08", "branch": "Main"},
			)
		self.assertEqual(len(data), 2)
		self.assertEqual(summary_value(summary, "Total Consultations"), 2)
		self.assertEqual(summary_value(summary, "Completion Rate"), 50)

	def test_consultation_completion_and_payment_cards(self):
		summary = report_insights.consultation_summary(
			[
				{"status": "Completed", "payment_status": "Paid", "planned_treatment_total": 120, "follow_up_date": "2026-07-10"},
				{"status": "In Progress", "payment_status": "Unpaid", "planned_treatment_total": 80},
				{"status": "Cancelled", "payment_status": "Not Billed", "planned_treatment_total": 0},
			]
		)
		self.assertEqual(summary_value(summary, "Total Consultations"), 3)
		self.assertEqual(summary_value(summary, "Completed"), 1)
		self.assertEqual(summary_value(summary, "Awaiting Payment"), 1)
		self.assertEqual(summary_value(summary, "Completion Rate"), 33.3)
		self.assertEqual(summary_value(summary, "Follow-up Required"), 1)

	def test_appointment_no_show_rate(self):
		summary = report_insights.build_report_summary(
			"Appointment Report",
			[
				{"status": "No Show"},
				{"status": "Completed", "linked_consultation": "VCON-1"},
				{"status": "Confirmed"},
				{"status": "No Show"},
			],
		)
		self.assertEqual(summary_value(summary, "No Show"), 2)
		self.assertEqual(summary_value(summary, "No-show Rate"), 50)
		self.assertEqual(summary_value(summary, "Converted to Consultation"), 1)

	def test_lab_completion_rate(self):
		summary = report_insights.lab_order_summary(
			[
				{"status": "Completed", "linked_invoice": "SINV-1"},
				{"status": "Pending"},
				{"status": "In Progress"},
			]
		)
		self.assertEqual(summary_value(summary, "Completed"), 1)
		self.assertEqual(summary_value(summary, "Completion Rate"), 33.3)
		self.assertEqual(summary_value(summary, "Unbilled / Unpaid Labs"), 2)

	def test_vaccination_due_overdue_administered_counts(self):
		summary = report_insights.vaccination_summary(
			[
				{"status": "Administered", "due_status": "Administered", "linked_invoice": "SINV-1"},
				{"status": "Administered", "due_status": "Due Soon"},
				{"status": "Administered", "due_status": "Overdue"},
				{"status": "Cancelled", "due_status": "Administered"},
			]
		)
		self.assertEqual(summary_value(summary, "Administered"), 3)
		self.assertEqual(summary_value(summary, "Due Soon"), 1)
		self.assertEqual(summary_value(summary, "Overdue"), 1)
		self.assertEqual(summary_value(summary, "Coverage Rate"), 75)

	def test_hospitalisation_occupancy_and_pending_action_cards(self):
		occupancy = report_insights.care_location_occupancy_summary(
			[
				{"capacity": 2, "active_occupancy": 1, "available_slots": 1, "status": "Available"},
				{"capacity": 2, "active_occupancy": 1, "available_slots": 1, "status": "Cleaning"},
			]
		)
		self.assertEqual(summary_value(occupancy, "Total Locations"), 2)
		self.assertEqual(summary_value(occupancy, "Occupied"), 2)
		self.assertEqual(summary_value(occupancy, "Occupancy Rate"), 50)

		actions = report_insights.pending_hospitalisation_actions_summary(
			[
				{"priority": "High", "action_type": "Pending Stock Posting"},
				{"priority": "Medium", "action_type": "Medication Due"},
			]
		)
		self.assertEqual(summary_value(actions, "Pending Actions"), 2)
		self.assertEqual(summary_value(actions, "Critical Actions"), 1)
		self.assertEqual(summary_value(actions, "Pending Stock Posting"), 1)

	def test_hospitalisation_report_wrappers_return_report_summary(self):
		from vetedge.veterinary.report.care_location_occupancy import care_location_occupancy
		from vetedge.veterinary.report.pending_hospitalisation_actions import pending_hospitalisation_actions

		with patch.object(
			care_location_occupancy,
			"get_care_location_occupancy_report",
			return_value=([], [{"capacity": 4, "active_occupancy": 2, "available_slots": 2, "status": "Available"}]),
		):
			result = care_location_occupancy.execute({"branch": "Main"})
		self.assertEqual(len(result), 5)
		self.assertEqual(summary_value(result[4], "Occupancy Rate"), 50)

		with patch.object(
			pending_hospitalisation_actions,
			"get_pending_hospitalisation_actions",
			return_value=([], []),
		):
			result = pending_hospitalisation_actions.execute({"branch": "Main"})
		self.assertEqual(len(result), 5)
		self.assertEqual(summary_value(result[4], "Pending Actions"), 0)

	def test_grooming_and_boarding_billing_cards(self):
		grooming = report_insights.grooming_summary(
			[
				{"status": "Completed", "total_charge": 100, "linked_invoice": "SINV-1", "grooming_service": "Bath"},
				{"status": "Scheduled", "total_charge": 0, "grooming_service": "Bath"},
			]
		)
		self.assertEqual(summary_value(grooming, "Grooming Revenue"), 100)
		self.assertEqual(summary_value(grooming, "Unpaid Grooming"), 1)
		self.assertEqual(summary_value(grooming, "Popular Service"), "Bath")

		boarding = report_insights.boarding_summary(
			[
				{"status": "Active", "total_boarding_charge": 300, "linked_invoice": "SINV-2"},
				{"status": "Booked", "total_boarding_charge": 0},
			]
		)
		self.assertEqual(summary_value(boarding, "Active Stays"), 1)
		self.assertEqual(summary_value(boarding, "Boarding Charges"), 300)
		self.assertEqual(summary_value(boarding, "Unbilled Boarding"), 1)

	def test_billing_summary_keeps_patient_outstanding_separate(self):
		summary = report_insights.revenue_summary(
			[
				{"grand_total": 1000, "paid_amount": 700, "outstanding_amount": 300, "status": "Partly Paid"},
			]
		)
		labels = {row["label"] for row in summary}
		self.assertIn("Current Service Outstanding", labels)
		self.assertNotIn("Patient Outstanding", labels)
		self.assertEqual(summary_value(summary, "Payment Completion Rate"), 70)

	def test_empty_dataset_does_not_crash(self):
		for report_name in (
			"Consultation Register",
			"Lab Order Report",
			"Vaccination Report",
			"Boarding Report",
			"Grooming Report",
			"Revenue Summary",
			"Care Location Occupancy",
			"Pending Hospitalisation Actions",
		):
			summary = report_insights.build_report_summary(report_name, [])
			self.assertTrue(summary)

	def test_no_private_coreedge_frontend_imports_are_introduced(self):
		from pathlib import Path

		root = Path(__file__).resolve().parents[2]
		public_js = root / "vetedge" / "public" / "js"
		report_js = root / "vetedge" / "veterinary" / "report"
		needles = ("edgeui.bundle", "coreedge/public", "coreedge/private", "private CoreEdge")
		for base in (public_js, report_js):
			for path in base.rglob("*.js"):
				text = path.read_text(encoding="utf-8")
				for needle in needles:
					self.assertNotIn(needle, text, str(path))


if __name__ == "__main__":
	unittest.main()
