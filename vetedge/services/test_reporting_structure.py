import unittest
from unittest.mock import patch
from types import SimpleNamespace

import frappe

frappe._ = lambda value: value

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

    def test_owner_register_respects_branch_filter(self):
        def get_all(doctype, filters=None, fields=None, order_by=None, group_by=None, pluck=None):
            if doctype == "Veterinary Patient":
                if pluck == "primary_owner" and isinstance(filters, dict) and filters.get("default_branch") == "Main":
                    return ["CUST-001"]
                if fields and group_by:
                    return [{"primary_owner": "CUST-001", "pet_count": 1}]
            if doctype == "Customer":
                return [
                    SimpleNamespace(name="CUST-001", customer_name="Jane Owner", get=lambda field: None),
                    SimpleNamespace(name="CUST-002", customer_name="John Owner", get=lambda field: None),
                ]
            if doctype == "Sales Invoice":
                self.assertEqual(filters["branch"], "Main")
                return [{"customer": "CUST-001", "outstanding_amount": 150}]
            return []

        frappe_stub = SimpleNamespace(
            db=SimpleNamespace(exists=lambda doctype, name: doctype == "DocType" and name == "Veterinary Patient"),
            get_all=get_all,
            get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname == "branch"),
            unscrub=lambda value: value.replace("_", " ").title(),
        )

        with (
            patch.object(reporting_structure, "frappe", frappe_stub),
            patch.object(reporting_structure, "_existing_field", side_effect=lambda doctype, fields: fields[0]),
        ):
            _, data, _, _, _ = reporting_structure._owner_register({"branch": "Main"})

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["owner"], "CUST-001")
        self.assertEqual(data[0]["outstanding_amount"], 150)


    def test_revenue_summary_branch_filter_uses_derived_invoice_context(self):
        invoice_rows = [
            {
                "name": "SINV-0001",
                "posting_date": "2026-05-01",
                "customer": "CUST-001",
                "branch": "",
                "cost_center": "",
                "grand_total": 100,
                "outstanding_amount": 25,
                "docstatus": 1,
                "status": "Unpaid",
            },
            {
                "name": "SINV-0002",
                "posting_date": "2026-05-01",
                "customer": "CUST-002",
                "branch": "",
                "cost_center": "",
                "grand_total": 200,
                "outstanding_amount": 0,
                "docstatus": 1,
                "status": "Paid",
            },
        ]
        invoice_context = {
            "SINV-0001": {"branch": "Branch A", "service_category": "Consultation"},
            "SINV-0002": {"branch": "Branch B", "service_category": "Consultation"},
        }

        with (
            patch.object(reporting_structure, "_get_sales_invoice_rows", return_value=invoice_rows),
            patch.object(reporting_structure, "_build_invoice_context_map", return_value=invoice_context),
        ):
            data = reporting_structure._build_revenue_summary_rows({"branch": "Branch A"})

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["invoice"], "SINV-0001")
        self.assertEqual(data[0]["branch"], "Branch A")
        self.assertEqual(data[0]["grand_total"], 100)


if __name__ == "__main__":
    unittest.main()
