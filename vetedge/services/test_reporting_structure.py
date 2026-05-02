import unittest
from unittest.mock import patch

from vetedge.services import reporting_structure


class TestReportingStructure(unittest.TestCase):
    def test_execute_structured_report_dispatches(self):
        with patch.object(reporting_structure, "_consultation_register", return_value=([], [], None, None, [])) as mocked:
            reporting_structure.execute_structured_report("Consultation Register", {})
        mocked.assert_called_once()

    def test_invoice_status_from_row(self):
        self.assertEqual(reporting_structure._invoice_status_from_row({"docstatus": 0, "outstanding_amount": 0}), "Draft")
        self.assertEqual(reporting_structure._invoice_status_from_row({"docstatus": 1, "outstanding_amount": 0}), "Paid")
        self.assertEqual(reporting_structure._invoice_status_from_row({"docstatus": 1, "outstanding_amount": 25}), "Unpaid")

    def test_vaccination_due_state(self):
        with patch("vetedge.services.reporting_structure.nowdate", return_value="2026-05-01"):
            self.assertEqual(reporting_structure._vaccination_due_state("2026-04-30", "Administered"), "Overdue")
            self.assertEqual(reporting_structure._vaccination_due_state("2026-05-10", "Administered"), "Due Soon")
            self.assertEqual(reporting_structure._vaccination_due_state("2026-06-20", "Administered"), "Administered")

    def test_infer_service_category(self):
        self.assertEqual(reporting_structure._infer_service_category("Boarding billing for stay", ""), "Boarding")
        self.assertEqual(reporting_structure._infer_service_category("Vaccination charge", ""), "Vaccination")
        self.assertEqual(reporting_structure._infer_service_category("Pet grooming service", ""), "Grooming")

    def test_revenue_summary_builds_totals(self):
        fake_rows = [
            {
                "invoice": "SINV-0001",
                "posting_date": "2026-05-01",
                "customer": "CUST-001",
                "branch": "Main",
                "cost_center": "Main - CC",
                "service_category": "Consultation",
                "grand_total": 100,
                "paid_amount": 80,
                "outstanding_amount": 20,
                "status": "Unpaid",
            }
        ]
        with patch.object(reporting_structure, "_build_revenue_summary_rows", return_value=fake_rows):
            columns, data, _, _, summary = reporting_structure._revenue_summary({})
        self.assertEqual(len(columns), 10)
        self.assertEqual(data[0]["invoice"], "SINV-0001")
        self.assertEqual(len(summary), 3)

    def test_kennel_availability_report_uses_helper(self):
        helper_rows = [
            {
                "kennel": "KEN-001",
                "branch": "Main",
                "capacity": 2,
                "current_occupancy": 1,
                "available_slots": 1,
                "status": "Occupied",
                "active_booking": "BOOK-001",
                "expected_check_out_date": "2026-05-04",
            }
        ]
        with patch("vetedge.services.boarding.get_kennel_availability", return_value=helper_rows):
            _, data, _, _, _ = reporting_structure._kennel_availability_report({"from_date": "2026-05-01", "to_date": "2026-05-07"})
        self.assertEqual(data[0]["kennel"], "KEN-001")
        self.assertEqual(data[0]["status"], "Occupied")


if __name__ == "__main__":
    unittest.main()
