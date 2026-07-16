import unittest
from unittest.mock import patch
from types import SimpleNamespace

import frappe

frappe._ = lambda value, *args, **kwargs: value

from vetedge.services import reporting_structure
from vetedge.services import reporting_logic_v4


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

    def test_revenue_summary_uses_cost_center_branch_when_invoice_branch_missing(self):
        invoice_rows = [
            {
                "name": "SINV-15000",
                "posting_date": "2026-06-09",
                "customer": "CUST-001",
                "branch": "",
                "cost_center": "",
                "grand_total": 15000,
                "outstanding_amount": 0,
                "docstatus": 1,
                "status": "Paid",
            }
        ]
        invoice_context = {"SINV-15000": {"cost_center": "Main - VED"}}

        with (
            patch.object(reporting_structure, "_get_sales_invoice_rows", return_value=invoice_rows),
            patch.object(reporting_structure, "_build_invoice_context_map", return_value=invoice_context),
            patch.object(reporting_structure, "_branch_from_cost_center", return_value="Main Branch"),
        ):
            data = reporting_structure._build_revenue_summary_rows({"from_date": "2026-06-01", "to_date": "2026-06-18"})

        self.assertEqual(data[0]["branch"], "Main Branch")
        self.assertEqual(data[0]["grand_total"], 15000)

    def test_revenue_summary_keeps_genuinely_branchless_invoice_unassigned(self):
        invoice_rows = [
            {
                "name": "SINV-BRANCHLESS",
                "posting_date": "2026-06-09",
                "customer": "CUST-001",
                "branch": "",
                "cost_center": "",
                "grand_total": 500,
                "outstanding_amount": 0,
                "docstatus": 1,
                "status": "Paid",
            }
        ]

        with (
            patch.object(reporting_structure, "_get_sales_invoice_rows", return_value=invoice_rows),
            patch.object(reporting_structure, "_build_invoice_context_map", return_value={}),
            patch.object(reporting_structure, "_branch_from_cost_center", return_value=""),
        ):
            data = reporting_structure._build_revenue_summary_rows({})

        self.assertEqual(data[0]["branch"], "Unassigned")

    def test_consultation_register_includes_consultation_type_column_and_unspecified(self):
        rows = [
            {
                "name": "VCON-001",
                "consultation_date": "2026-06-15",
                "patient": "VP-001",
                "owner": "CUST-001",
                "practitioner": "Dr Ada",
                "practitioner_user": "doctor@example.com",
                "service_branch": "Main",
                "consultation_type": "",
                "status": "Completed",
                "linked_invoice": None,
                "linked_appointment": "VAPT-001",
                "payment_status": "Paid",
                "follow_up_date": None,
                "follow_up_appointment": None,
                "assessment_notes": "<p>Stable patient</p>",
                "created_by": "doctor@example.com",
            },
            {
                "name": "VCON-002",
                "consultation_date": "2026-06-15",
                "patient": "VP-002",
                "owner": "CUST-002",
                "practitioner": "Dr Ben",
                "practitioner_user": "doctor2@example.com",
                "service_branch": "Main",
                "consultation_type": "House Call",
                "status": "Completed",
                "linked_invoice": None,
                "linked_appointment": None,
                "payment_status": "Not Billed",
                "follow_up_date": "2026-06-20",
                "follow_up_appointment": "VAPT-002",
                "assessment_notes": None,
                "created_by": "doctor2@example.com",
            },
        ]

        with (
            patch.object(reporting_structure, "_get_consultation_rows", return_value=rows),
            patch.object(reporting_structure, "_get_patient_title_map", return_value={}),
            patch.object(reporting_structure, "_get_user_full_name_map", return_value={}),
            patch.object(reporting_structure, "_get_consultation_invoice_map", return_value={}),
            patch.object(reporting_structure, "_get_invoice_status_map", return_value={}),
            patch.object(reporting_structure, "_get_consultation_planned_totals", return_value={"VCON-001": 2500}),
            patch.object(reporting_structure, "_get_consultation_vaccination_counts", return_value={"VCON-001": 1}),
        ):
            columns, data, _, _, _ = reporting_structure._consultation_register({})

        self.assertIn("consultation_type", {column["fieldname"] for column in columns})
        self.assertIn("payment_status", {column["fieldname"] for column in columns})
        self.assertIn("outcome_assessment_summary", {column["fieldname"] for column in columns})
        self.assertEqual(data[0]["consultation_type"], "Unspecified")
        self.assertEqual(data[1]["consultation_type"], "House Call")
        self.assertEqual(data[0]["planned_treatment_total"], 2500)
        self.assertEqual(data[0]["has_vaccination"], "Yes")
        self.assertEqual(data[0]["outcome_assessment_summary"], "Stable patient")

    def test_get_consultation_rows_applies_consultation_type_and_branch_filters(self):
        captured = {}

        def get_all(doctype, filters=None, fields=None, order_by=None):
            captured["doctype"] = doctype
            captured["filters"] = filters
            captured["fields"] = fields
            return [
                {
                    "name": "VCON-001",
                    "consultation_datetime": "2026-06-15 09:00:00",
                    "patient": "VP-001",
                    "primary_owner": "CUST-001",
                    "consulting_practitioner": "doctor@example.com",
                    "consulting_practitioner_name": "Dr Ada",
                    "service_branch": "Main",
                    "consultation_type": "House Call",
                    "status": "Completed",
                    "linked_invoice": None,
                    "linked_appointment": "VAPT-001",
                    "payment_status": "Paid",
                    "follow_up_date": None,
                    "follow_up_appointment": None,
                    "assessment_notes": "Stable",
                    "owner": "doctor@example.com",
                }
            ]

        consultation_fields = {
            "consultation_datetime",
            "patient",
            "primary_owner",
            "consulting_practitioner",
            "consulting_practitioner_name",
            "service_branch",
            "consultation_type",
            "status",
            "linked_invoice",
            "linked_appointment",
            "payment_status",
            "follow_up_date",
            "follow_up_appointment",
            "assessment_notes",
            "owner",
        }
        meta = SimpleNamespace(get_field=lambda fieldname: fieldname in consultation_fields)
        frappe_stub = SimpleNamespace(
            db=SimpleNamespace(exists=lambda doctype, name=None: doctype == "DocType" and name == "Veterinary Consultation"),
            get_meta=lambda doctype: meta,
            get_all=get_all,
        )

        with patch.object(reporting_structure, "frappe", frappe_stub):
            rows = reporting_structure._get_consultation_rows(
                {
                    "from_date": "2026-06-01",
                    "to_date": "2026-06-30",
                    "branch": "Main",
                    "consultation_type": "House Call",
                    "payment_status": "Paid",
                    "created_by": "doctor@example.com",
                }
            )

        self.assertEqual(captured["doctype"], "Veterinary Consultation")
        self.assertEqual(captured["filters"]["service_branch"], "Main")
        self.assertEqual(captured["filters"]["consultation_type"], "House Call")
        self.assertEqual(captured["filters"]["payment_status"], "Paid")
        self.assertEqual(captured["filters"]["owner"], "doctor@example.com")
        self.assertIn("consultation_datetime", captured["fields"])
        self.assertIn("consultation_type", captured["fields"])
        self.assertEqual(rows[0]["consultation_type"], "House Call")

    def test_executive_dashboard_includes_consultation_type_breakdown(self):
        consultation_rows = [
            {"consultation_date": "2026-06-15", "service_branch": "Main", "consultation_type": "General Consultation"},
            {"consultation_date": "2026-06-15", "service_branch": "Main", "consultation_type": "House Call"},
            {"consultation_date": "2026-06-15", "service_branch": "Branch B", "consultation_type": ""},
        ]

        def rows(report_name, filters):
            if report_name == "Consultation Register":
                if filters.get("branch") == "Main":
                    return [row for row in consultation_rows if row["service_branch"] == "Main"]
                return consultation_rows
            return []

        frappe_stub = SimpleNamespace(_dict=frappe._dict, format_value=lambda value, options: value)

        with (
            patch.object(reporting_logic_v4, "frappe", frappe_stub),
            patch.object(reporting_logic_v4, "nowdate", return_value="2026-06-15"),
            patch.object(reporting_logic_v4, "validate_dashboard_access"),
            patch.object(reporting_logic_v4, "normalize_dashboard_filters", side_effect=lambda key, filters: frappe._dict(filters or {})),
            patch.object(reporting_logic_v4, "_rows", side_effect=rows),
            patch.object(reporting_logic_v4, "_appointments_today", return_value=0),
            patch.object(reporting_logic_v4, "_active_patients", return_value=0),
        ):
            payload = reporting_logic_v4.get_dashboard_payload("executive", {"branch": "Main"})

        chart = next(chart for chart in payload["charts"] if chart["title"] == "Consultations by Type")
        self.assertEqual(chart["type"], "donut")
        self.assertEqual(chart["data"]["labels"], ["General Consultation", "House Call"])
        self.assertEqual(chart["data"]["datasets"][0]["values"], [1, 1])

    def test_consultation_type_chart_groups_unspecified(self):
        chart = reporting_logic_v4._consultation_type_chart(
            [
                {"consultation_type": "House Call"},
                {"consultation_type": ""},
                {"consultation_type": None},
            ]
        )

        self.assertEqual(chart["data"]["labels"], ["House Call", "Unspecified"])
        self.assertEqual(chart["data"]["datasets"][0]["values"], [1, 2])

    def test_planned_treatment_report_returns_quantities_amounts_and_totals(self):
        consultation_rows = [
            {
                "name": "VCON-001",
                "consultation_date": "2026-06-15 09:00:00",
                "patient": "VP-001",
                "owner": "CUST-001",
                "practitioner": "Dr Ada",
                "practitioner_user": "doctor@example.com",
                "service_branch": "Main",
                "consultation_type": "House Call",
                "status": "Completed",
            },
            {
                "name": "VCON-002",
                "consultation_date": "2026-06-16 09:00:00",
                "patient": "VP-001",
                "owner": "CUST-001",
                "practitioner": "Dr Ada",
                "practitioner_user": "doctor@example.com",
                "service_branch": "Main",
                "consultation_type": "General Consultation",
                "status": "Completed",
            },
        ]
        treatment_rows = [
            frappe._dict(parent="VCON-001", item="ITEM-001", qty=2, uom="Nos", rate=1000, amount=2000, notes="Dose A", service_type=None, treatment_type=None),
            frappe._dict(parent="VCON-001", item="ITEM-002", qty=1, uom="Nos", rate=500, amount=0, notes="Dose B", service_type=None, treatment_type=None),
            frappe._dict(parent="VCON-002", item="ITEM-003", qty=1, uom="Nos", rate=300, amount=300, notes="", service_type=None, treatment_type=None),
        ]

        frappe_stub = SimpleNamespace(
            db=SimpleNamespace(exists=lambda doctype, name=None: (doctype, name) == ("DocType", "Planned Treatment Item")),
            get_all=lambda *args, **kwargs: treatment_rows,
            unscrub=lambda value: value.replace("_", " ").title(),
        )

        with (
            patch.object(reporting_structure, "frappe", frappe_stub),
            patch.object(reporting_structure, "_get_consultation_rows", return_value=consultation_rows),
            patch.object(reporting_structure, "_get_patient_title_map", return_value={"VP-001": "Buddy"}),
            patch.object(reporting_structure, "_get_user_full_name_map", return_value={"doctor@example.com": "Dr Ada Vet"}),
        ):
            columns, data, _, _, summary = reporting_structure._planned_treatment_report({"item": "ITEM-001"})

        self.assertIn("consultation_total", {column["fieldname"] for column in columns})
        self.assertEqual(data[0]["qty"], 2)
        self.assertEqual(data[0]["amount"], 2000)
        self.assertEqual(data[1]["amount"], 500)
        self.assertEqual(data[0]["consultation_total"], 2500)
        self.assertEqual(data[0]["patient_total"], 2800)
        self.assertEqual(summary[0]["value"], 2800)

    def test_planned_treatment_report_passes_filters_to_consultation_rows(self):
        captured = {}

        def get_consultation_rows(filters):
            captured.update(filters)
            return []

        with patch.object(reporting_structure, "_get_consultation_rows", side_effect=get_consultation_rows):
            reporting_structure._build_planned_treatment_rows(
                {
                    "from_date": "2026-06-01",
                    "to_date": "2026-06-30",
                    "branch": "Main",
                    "practitioner": "doctor@example.com",
                    "patient": "VP-001",
                    "consultation_type": "House Call",
                    "consultation_status": "Completed",
                }
            )

        self.assertEqual(captured["branch"], "Main")
        self.assertEqual(captured["practitioner"], "doctor@example.com")
        self.assertEqual(captured["patient"], "VP-001")
        self.assertEqual(captured["consultation_type"], "House Call")
        self.assertEqual(captured["consultation_status"], "Completed")

    def test_financial_dashboard_payload_returns_safely_without_finance_data(self):
        frappe_stub = SimpleNamespace(_dict=frappe._dict, format_value=lambda value, options: value)

        with (
            patch.object(reporting_logic_v4, "frappe", frappe_stub),
            patch.object(reporting_logic_v4, "nowdate", return_value="2026-06-15"),
            patch.object(reporting_logic_v4, "validate_dashboard_access"),
            patch.object(reporting_logic_v4, "normalize_dashboard_filters", side_effect=lambda key, filters: frappe._dict(filters or {})),
            patch.object(reporting_logic_v4, "_rows", return_value=[]),
        ):
            payload = reporting_logic_v4.get_dashboard_payload("financial", {})

        self.assertEqual(payload["dashboard_key"], "financial")
        self.assertEqual(
            [kpi["label"] for kpi in payload["kpis"]],
            [
                "Total Revenue",
                "Paid Revenue",
                "Outstanding Revenue",
                "Draft / Pending Invoices",
                "Payments Received",
            ],
        )
        self.assertIn("Revenue by Service Area", [chart["title"] for chart in payload["charts"]])

    def test_hospitalisation_dashboard_payload_returns_safely_without_active_stays(self):
        frappe_stub = SimpleNamespace(_dict=frappe._dict, format_value=lambda value, options: value)

        with (
            patch.object(reporting_logic_v4, "frappe", frappe_stub),
            patch.object(reporting_logic_v4, "nowdate", return_value="2026-06-15"),
            patch.object(reporting_logic_v4, "validate_dashboard_access"),
            patch.object(reporting_logic_v4, "normalize_dashboard_filters", side_effect=lambda key, filters: frappe._dict(filters or {})),
            patch("vetedge.services.hospitalisation_reports.get_active_hospitalisations", return_value=([], [])),
            patch("vetedge.services.hospitalisation_reports.get_hospitalisation_charge_report", return_value=([], [])),
            patch("vetedge.services.hospitalisation_reports.get_care_location_occupancy_report", return_value=([], [])),
            patch("vetedge.services.hospitalisation_reports.get_discharge_watch_report", return_value=([], [])),
            patch("vetedge.services.hospitalisation_reports.get_pending_hospitalisation_actions", return_value=([], [])),
        ):
            payload = reporting_logic_v4.get_dashboard_payload("hospitalisation", {})

        self.assertEqual(payload["dashboard_key"], "hospitalisation")
        self.assertEqual(payload["title"], "Hospitalisation Dashboard")
        self.assertEqual(payload["kpis"][0], {"label": "Active Hospitalisations", "value": 0})
        charts = {chart["title"]: chart for chart in payload["charts"]}
        self.assertEqual(charts["Pending Hospitalisation Actions"]["empty_state"], "No pending hospitalisation actions.")
        self.assertEqual(charts["Pending Hospitalisation Actions"]["rows"], [])
        self.assertEqual(charts["Care Location Occupancy"]["empty_state"], "No care location occupancy data available.")
        self.assertEqual(charts["Care Location Occupancy"]["rows"], [])

    def test_hospitalisation_dashboard_payload_includes_occupancy_chart_and_table_rows(self):
        frappe_stub = SimpleNamespace(_dict=frappe._dict, format_value=lambda value, options: value)
        occupancy_rows = [
            {
                "care_location": "Ward A",
                "status": "Occupied",
                "active_occupancy": 2,
                "capacity": 4,
                "available_slots": 2,
            }
        ]

        with (
            patch.object(reporting_logic_v4, "frappe", frappe_stub),
            patch.object(reporting_logic_v4, "nowdate", return_value="2026-06-15"),
            patch.object(reporting_logic_v4, "validate_dashboard_access"),
            patch.object(reporting_logic_v4, "normalize_dashboard_filters", side_effect=lambda key, filters: frappe._dict(filters or {})),
            patch("vetedge.services.hospitalisation_reports.get_active_hospitalisations", return_value=([], [])),
            patch("vetedge.services.hospitalisation_reports.get_hospitalisation_charge_report", return_value=([], [])),
            patch("vetedge.services.hospitalisation_reports.get_care_location_occupancy_report", return_value=([], occupancy_rows)),
            patch("vetedge.services.hospitalisation_reports.get_discharge_watch_report", return_value=([], [])),
            patch("vetedge.services.hospitalisation_reports.get_pending_hospitalisation_actions", return_value=([], [])),
        ):
            payload = reporting_logic_v4.get_dashboard_payload("hospitalisation", {})

        occupancy_kpi = next(kpi for kpi in payload["kpis"] if kpi["label"] == "Care Location Occupancy")
        occupancy_chart = next(chart for chart in payload["charts"] if chart["title"] == "Care Location Occupancy")
        self.assertEqual(occupancy_kpi["value"], "2 / 4 (50.0%)")
        self.assertEqual(occupancy_chart["data"]["labels"], ["Ward A"])
        self.assertEqual(occupancy_chart["data"]["datasets"][0]["values"], [2])
        self.assertEqual(occupancy_chart["rows"][0]["care_location"], "Ward A")
        self.assertEqual(occupancy_chart["rows"][0]["available_slots"], 2)

    def test_hospitalisation_dashboard_payload_empty_pending_actions_has_safe_empty_state(self):
        chart = reporting_logic_v4._chart("Pending Hospitalisation Actions", "bar", [], [], "#f59e0b")
        chart.update({"empty_state": "No pending hospitalisation actions.", "rows": []})

        self.assertEqual(chart["data"]["labels"], [])
        self.assertEqual(chart["rows"], [])
        self.assertEqual(chart["empty_state"], "No pending hospitalisation actions.")


class TestFinancialDatasetUnification(unittest.TestCase):
    def test_financial_dataset_and_dashboard_reconciliation(self):
        invoices = [
            frappe._dict(name="SINV-001", posting_date="2026-07-05", company="Company A", customer="CUST-001", grand_total=1000.0, outstanding_amount=400.0, docstatus=1, due_date="2026-07-20", branch=None, cost_center="CC-A", status="Unpaid"),
            frappe._dict(name="SINV-002", posting_date="2026-07-10", company="Company A", customer="CUST-002", grand_total=500.0, outstanding_amount=0.0, docstatus=1, due_date="2026-07-25", branch=None, cost_center="CC-B", status="Paid"),
            frappe._dict(name="SINV-003", posting_date="2026-07-12", company="Company A", customer="CUST-001", grand_total=300.0, outstanding_amount=300.0, docstatus=0, due_date="2026-07-30", branch="Branch A", cost_center="CC-A", status="Draft"),
            frappe._dict(name="SINV-004", posting_date="2026-07-14", company="Company A", customer="CUST-003", grand_total=1200.0, outstanding_amount=1200.0, docstatus=1, due_date="2026-07-28", branch=None, cost_center="CC-A", status="Unpaid"),
        ]

        consultations = [
            frappe._dict(name="VCON-001", sales_invoice="SINV-001", linked_invoice="SINV-001", invoice="SINV-001", patient="VP-001", service_branch="Branch A", branch=None, cost_center="CC-A")
        ]

        vaccinations = [
            frappe._dict(name="VVAC-001", linked_invoice="SINV-004", patient="VP-002", service_branch="Branch A", branch=None, cost_center="CC-A")
        ]

        branch_by_cc = {"CC-B": "Branch B", "CC-A": "Branch A"}

        def db_exists(doctype, name=None):
            return doctype in {
                "DocType", "Sales Invoice", "Veterinary Consultation", 
                "Veterinary Vaccination Record", "Branch", 
                "Consultation Invoice Reference", "Veterinary Billing Session Charge"
            }

        def get_all(doctype, filters=None, fields=None, order_by=None, **kwargs):
            if doctype == "Sales Invoice":
                res = invoices
                from_date = filters.get("posting_date")
                if from_date:
                    if isinstance(from_date, tuple) and from_date[0] == "between":
                        d_range = from_date[1]
                        res = [r for r in res if d_range[0] <= r.posting_date <= d_range[1]]
                if filters.get("company"):
                    res = [r for r in res if r.company == filters.get("company")]
                return res
            elif doctype == "Veterinary Consultation":
                if filters:
                    inv_key = next((k for k in filters if k in ("sales_invoice", "linked_invoice", "invoice")), None)
                    if inv_key:
                        inv_val = filters[inv_key]
                        inv_in = inv_val[1] if isinstance(inv_val, tuple) else inv_val
                        if not isinstance(inv_in, (list, tuple)):
                            inv_in = [inv_in]
                        return [c for c in consultations if c.sales_invoice in inv_in or c.get(inv_key) in inv_in]
                return consultations
            elif doctype == "Veterinary Vaccination Record":
                if filters:
                    inv_key = next((k for k in filters if k in ("sales_invoice", "linked_invoice", "invoice")), None)
                    if inv_key:
                        inv_val = filters[inv_key]
                        inv_in = inv_val[1] if isinstance(inv_val, tuple) else inv_val
                        if not isinstance(inv_in, (list, tuple)):
                            inv_in = [inv_in]
                        return [v for v in vaccinations if v.linked_invoice in inv_in or v.get(inv_key) in inv_in]
                return vaccinations
            elif doctype == "Branch":
                return [frappe._dict(name="Branch A", cost_center="CC-A"), frappe._dict(name="Branch B", cost_center="CC-B")]
            return []

        from vetedge.services.financial_dataset import build_financial_dataset

        with (
            patch("vetedge.services.reporting_structure.frappe.db.exists", side_effect=db_exists),
            patch("vetedge.services.reporting_structure.frappe.get_all", side_effect=get_all),
            patch("vetedge.services.reporting_structure._branch_from_cost_center", side_effect=lambda cc: branch_by_cc.get(cc, "")),
            patch("vetedge.services.reporting_structure._get_invoice_payment_branch_map", return_value={}),
            patch("vetedge.services.reporting_structure._existing_field", side_effect=lambda dt, candidates: candidates[0]),
        ):
            # Test 1: Fetch financial dataset with no filters (defaults to date range)
            dataset = build_financial_dataset({"from_date": "2026-07-01", "to_date": "2026-07-15"})
            self.assertEqual(len(dataset), 4)

            # Check derived branch, patient, and service source
            inv1 = next(r for r in dataset if r["sales_invoice"] == "SINV-001")
            self.assertEqual(inv1["branch"], "Branch A")
            self.assertEqual(inv1["patient"], "VP-001")
            self.assertEqual(inv1["service_source"], "Consultation")

            inv2 = next(r for r in dataset if r["sales_invoice"] == "SINV-002")
            self.assertEqual(inv2["branch"], "Branch B")
            self.assertEqual(inv2["service_source"], "General")

            inv4 = next(r for r in dataset if r["sales_invoice"] == "SINV-004")
            self.assertEqual(inv4["branch"], "Branch A")
            self.assertEqual(inv4["patient"], "VP-002")
            self.assertEqual(inv4["service_source"], "Vaccination")

            # Test 2: Filter by Branch A
            dataset_branch_a = build_financial_dataset({"from_date": "2026-07-01", "to_date": "2026-07-15", "branch": "Branch A"})
            self.assertEqual(len(dataset_branch_a), 3)

            # Test 3: Dashboard & KPI reconciliation
            frappe_stub = SimpleNamespace(
                _dict=frappe._dict,
                format_value=lambda val, opts=None: val,
                db=SimpleNamespace(exists=db_exists, count=lambda dt, filt: 0),
                get_all=get_all
            )

            from vetedge.services.reporting_logic_v3 import execute_structured_report

            def mock_execute_report(report_name, filters=None):
                from vetedge.services.reporting_structure import execute_structured_report as base_exec
                with (
                    patch("vetedge.services.reporting_structure.frappe.db.exists", side_effect=db_exists),
                    patch("vetedge.services.reporting_structure.frappe.get_all", side_effect=get_all),
                    patch("vetedge.services.reporting_structure._branch_from_cost_center", side_effect=lambda cc: branch_by_cc.get(cc, "")),
                    patch("vetedge.services.reporting_structure._get_invoice_payment_branch_map", return_value={}),
                    patch("vetedge.services.reporting_structure._existing_field", side_effect=lambda dt, candidates: candidates[0]),
                ):
                    return base_exec(report_name, filters)

            from vetedge.services import reporting_logic_v4

            with (
                patch.object(reporting_logic_v4, "frappe", frappe_stub),
                patch.object(reporting_logic_v4, "nowdate", return_value="2026-07-15"),
                patch.object(reporting_logic_v4, "validate_dashboard_access"),
                patch.object(reporting_logic_v4, "normalize_dashboard_filters", side_effect=lambda key, filters: frappe._dict(filters or {})),
                patch("vetedge.services.reporting_logic_v4.execute_structured_report", side_effect=mock_execute_report),
            ):
                payload = reporting_logic_v4.get_dashboard_payload("financial", {"from_date": "2026-07-01", "to_date": "2026-07-15", "branch": "Branch A"})

                total_rev_kpi = next(k for k in payload["kpis"] if k["label"] == "Total Revenue")
                paid_rev_kpi = next(k for k in payload["kpis"] if k["label"] == "Paid Revenue")
                out_rev_kpi = next(k for k in payload["kpis"] if k["label"] == "Outstanding Revenue")
                draft_kpi = next(k for k in payload["kpis"] if k["label"] == "Draft / Pending Invoices")

                # Reconcile sum aggregations
                self.assertEqual(total_rev_kpi["value"], 2200.0)
                self.assertEqual(paid_rev_kpi["value"], 600.0)
                self.assertEqual(out_rev_kpi["value"], 1600.0)
                self.assertEqual(draft_kpi["value"], 1)

                # Total = Paid + Outstanding
                self.assertEqual(total_rev_kpi["value"], paid_rev_kpi["value"] + out_rev_kpi["value"])

                # Check action metadata navigation targets
                self.assertEqual(out_rev_kpi["action"]["target"], "Unpaid Invoice Report")
                self.assertEqual(draft_kpi["action"]["target"], "Unpaid Invoice Report")
                self.assertEqual(draft_kpi["action"]["filters"]["status"], "Draft")


class TestFinancialInsights(unittest.TestCase):
    def test_financial_insights_reconciliation_and_schema(self):
        invoices = [
            frappe._dict(name="SINV-001", posting_date="2026-07-05", company="Company A", customer="CUST-001", grand_total=1000.0, outstanding_amount=400.0, docstatus=1, due_date="2026-07-20", branch="Branch A", cost_center="CC-A", status="Unpaid"),
            frappe._dict(name="SINV-002", posting_date="2026-07-10", company="Company A", customer="CUST-002", grand_total=500.0, outstanding_amount=0.0, docstatus=1, due_date="2026-07-25", branch="Branch B", cost_center="CC-B", status="Paid"),
            frappe._dict(name="SINV-003", posting_date="2026-07-12", company="Company A", customer="CUST-001", grand_total=300.0, outstanding_amount=300.0, docstatus=0, due_date="2026-07-30", branch="Branch A", cost_center="CC-A", status="Draft"),
        ]

        branch_by_cc = {"CC-B": "Branch B", "CC-A": "Branch A"}

        def db_exists(doctype, name=None):
            return doctype in {"DocType", "Sales Invoice", "Veterinary Consultation", "Branch", "Payment Entry Reference", "Payment Entry"}

        def get_all(doctype, filters=None, fields=None, order_by=None, **kwargs):
            if doctype == "Sales Invoice":
                res = invoices
                from_date = filters.get("posting_date")
                if from_date:
                    if isinstance(from_date, tuple) and from_date[0] == "between":
                        d_range = from_date[1]
                        res = [r for r in res if d_range[0] <= r.posting_date <= d_range[1]]
                if filters.get("company"):
                    res = [r for r in res if r.company == filters.get("company")]
                return res
            elif doctype == "Payment Entry Reference":
                return [frappe._dict(reference_name="SINV-002", parent="PE-001")]
            elif doctype == "Payment Entry":
                return [frappe._dict(name="PE-001", posting_date="2026-07-12", branch="Branch B")]
            elif doctype == "Branch":
                return [frappe._dict(name="Branch A", cost_center="CC-A"), frappe._dict(name="Branch B", cost_center="CC-B")]
            return []

        from vetedge.services.financial_insights import get_financial_insights

        with (
            patch("vetedge.services.financial_dataset.frappe.db.exists", side_effect=db_exists),
            patch("vetedge.services.financial_dataset.frappe.get_all", side_effect=get_all),
            patch("vetedge.services.reporting_structure._branch_from_cost_center", side_effect=lambda cc: branch_by_cc.get(cc, "")),
            patch("vetedge.services.reporting_structure.frappe.db.exists", side_effect=db_exists),
            patch("vetedge.services.reporting_structure.frappe.get_all", side_effect=get_all),
            patch("vetedge.services.reporting_structure._existing_field", side_effect=lambda dt, candidates: candidates[0]),
            patch("vetedge.services.financial_insights.frappe.db.exists", side_effect=db_exists),
            patch("vetedge.services.financial_insights.frappe.get_all", side_effect=get_all),
        ):
            insights = get_financial_insights({"from_date": "2026-07-01", "to_date": "2026-07-15"})

            kpis = insights["kpis"]
            self.assertEqual(len(kpis), 5)

            total_revenue = next(k for k in kpis if k["id"] == "total_revenue")
            paid_revenue = next(k for k in kpis if k["id"] == "paid_revenue")
            outstanding_revenue = next(k for k in kpis if k["id"] == "outstanding_revenue")

            self.assertEqual(total_revenue["value"], 1500.0)
            self.assertEqual(paid_revenue["value"], 1100.0)
            self.assertEqual(outstanding_revenue["value"], 400.0)

            # Reconcile Math
            self.assertEqual(total_revenue["value"], paid_revenue["value"] + outstanding_revenue["value"])

            # Check Schema validations
            for card in kpis + insights["collection_metrics"] + insights["revenue_composition"] + insights["health_indicators"]:
                self.assertIn("id", card)
                self.assertIn("title", card)
                self.assertIn("value", card)
                self.assertIn("secondary_value", card)
                self.assertIn("trend", card)
                self.assertIn("tooltip", card)
                self.assertIn("severity", card)
                self.assertIn("category", card)

            # Check Collection performance
            coll_metrics = insights["collection_metrics"]
            cr = next(m for m in coll_metrics if m["id"] == "collection_rate")
            self.assertEqual(cr["value"], 1100.0 / 1500.0 * 100.0)

            # Check Average Days to Payment
            dp = next(m for m in coll_metrics if m["id"] == "avg_days_payment")
            self.assertEqual(dp["value"], 2.0)

            # Check Health Indicators
            health = insights["health_indicators"]
            self.assertTrue(any(h["id"] == "billing_completion_rate" for h in health))
            self.assertTrue(any(h["id"] == "payment_completion_rate" for h in health))
            self.assertTrue(any(h["id"] == "revenue_concentration" for h in health))

    def test_financial_insights_handles_empty_dataset_gracefully(self):
        from vetedge.services.financial_insights import get_financial_insights

        def get_empty(*args, **kwargs):
            return []

        with (
            patch("vetedge.services.financial_dataset.frappe.db.exists", return_value=True),
            patch("vetedge.services.financial_dataset.frappe.get_all", side_effect=get_empty),
            patch("vetedge.services.reporting_structure._get_sales_invoice_rows", return_value=[]),
        ):
            insights = get_financial_insights({"from_date": "2026-07-01", "to_date": "2026-07-15"})

            total_rev = next(k for k in insights["kpis"] if k["id"] == "total_revenue")
            cr = next(m for m in insights["collection_metrics"] if m["id"] == "collection_rate")

            self.assertEqual(total_rev["value"], 0.0)
            self.assertEqual(cr["value"], 0.0)


    def test_financial_card_semantic_types(self):
        from vetedge.services.financial_insights import _build_collection_metrics, _build_summary_cards

        current = {"total_revenue": 100, "paid_revenue": 80, "outstanding_revenue": 20, "invoice_count": 1,
                   "paid_invoice_count": 1, "unpaid_invoice_count": 0, "overdue_invoice_count": 0,
                   "draft_invoice_count": 2, "draft_invoice_value": 50, "avg_days_payment": 1}
        cards = _build_summary_cards(current, current, {}) + _build_collection_metrics(current, current)
        types = {card["id"]: card["value_type"] for card in cards}
        self.assertEqual(types["draft_invoices"], "integer")
        self.assertEqual(types["total_revenue"], "currency")
        self.assertEqual(types["outstanding_revenue"], "currency")
        self.assertEqual(types["collection_rate"], "percent")
        self.assertEqual(types["avg_days_payment"], "float")


    def test_dashboard_chart_semantic_types(self):
        from vetedge.services import reporting_logic_v4
        from vetedge.services import reporting_structure

        financial = reporting_logic_v4._daily_revenue_chart([{"posting_date": "2026-07-16", "grand_total": 2500}])
        counts = reporting_logic_v4._consultation_chart([{"consultation_date": "2026-07-16"}])
        branch_revenue = reporting_structure._chart("Revenue by Branch", "bar", ["Main"], [2500], "#10b981", "currency")

        self.assertEqual(financial["value_type"], "currency")
        self.assertEqual(financial["fieldtype"], "Currency")
        self.assertEqual(counts["value_type"], "integer")
        self.assertEqual(counts["fieldtype"], "Int")
        self.assertEqual(branch_revenue["value_type"], "currency")


    def test_revenue_composition_uses_raw_currency_values_and_shares(self):
        from vetedge.services.financial_insights import _build_revenue_composition

        composition = _build_revenue_composition({
            "total_revenue": 648300.0,
            "revenue_by_service": {"Consultation": 284300.0, "Lab": 160500.0, "Vaccination": 150000.0, "Other": 53500.0},
        })
        self.assertEqual(sum(card["value"] for card in composition), 648300.0)
        self.assertTrue(all(card["value_type"] == "currency" for card in composition))
        self.assertTrue(all(isinstance(card["value"], float) for card in composition))
        self.assertEqual(composition[0]["title"], "Consultation")
        self.assertAlmostEqual(sum(card["share_percent"] for card in composition), 100.0, places=0)


if __name__ == "__main__":
    import unittest
    unittest.main()
