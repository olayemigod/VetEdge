from __future__ import annotations

import unittest
from unittest.mock import patch

import frappe

from vetedge.services import owner_register_optimized, reporting_logic_v3


class TestOwnerRegisterPerformance(unittest.TestCase):
    def test_branch_filter_scopes_aggregates_without_changing_pet_count_semantics(self):
        calls = []

        def get_all(doctype, filters=None, fields=None, order_by=None, group_by=None, pluck=None, **_kwargs):
            calls.append((doctype, filters, fields, group_by, pluck))
            if doctype == "Veterinary Patient" and pluck == "primary_owner":
                self.assertEqual(filters, {"default_branch": "Main"})
                return ["CUST-001"]
            if doctype == "Customer":
                self.assertEqual(filters, {"name": ("in", ["CUST-001"])})
                return [frappe._dict(name="CUST-001", customer_name="Jane Owner")]
            if doctype == "Veterinary Patient" and group_by == "primary_owner":
                self.assertEqual(filters, {"primary_owner": ("in", ["CUST-001"])})
                self.assertNotIn("default_branch", filters)
                return [frappe._dict(primary_owner="CUST-001", pet_count=3)]
            if doctype == "Sales Invoice":
                self.assertEqual(filters["customer"], ("in", ["CUST-001"]))
                self.assertEqual(filters["branch"], "Main")
                return [frappe._dict(customer="CUST-001", outstanding_amount=150)]
            return []

        with (
            patch.object(owner_register_optimized.frappe, "get_all", side_effect=get_all),
            patch.object(
                owner_register_optimized.frappe.db,
                "exists",
                side_effect=lambda doctype, name=None: doctype == "DocType" and name == "Veterinary Patient",
            ),
            patch.object(
                owner_register_optimized.frappe,
                "get_meta",
                return_value=frappe._dict(has_field=lambda fieldname: fieldname == "branch"),
            ),
            patch.object(owner_register_optimized, "_existing_field", side_effect=lambda _doctype, fields: fields[0]),
        ):
            _, data, _, _, _ = owner_register_optimized.execute_owner_register({"branch": "Main"})

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["owner"], "CUST-001")
        self.assertEqual(data[0]["number_of_pets"], 3)
        self.assertEqual(data[0]["outstanding_amount"], 150)
        self.assertTrue(any(call[0] == "Veterinary Patient" and call[3] == "primary_owner" for call in calls))

    def test_unfiltered_report_keeps_unscoped_grouped_aggregate_shape(self):
        def get_all(doctype, filters=None, fields=None, order_by=None, group_by=None, pluck=None, **_kwargs):
            if doctype == "Customer":
                self.assertEqual(filters, {})
                return [
                    frappe._dict(name="CUST-001", customer_name="Jane Owner"),
                    frappe._dict(name="CUST-002", customer_name="John Owner"),
                ]
            if doctype == "Veterinary Patient" and group_by == "primary_owner":
                self.assertEqual(filters, {})
                return [
                    frappe._dict(primary_owner="CUST-001", pet_count=2),
                    frappe._dict(primary_owner="CUST-002", pet_count=1),
                ]
            if doctype == "Sales Invoice":
                self.assertNotIn("customer", filters)
                return []
            return []

        with (
            patch.object(owner_register_optimized.frappe, "get_all", side_effect=get_all),
            patch.object(
                owner_register_optimized.frappe.db,
                "exists",
                side_effect=lambda doctype, name=None: doctype == "DocType" and name == "Veterinary Patient",
            ),
            patch.object(owner_register_optimized, "_existing_field", side_effect=lambda _doctype, fields: fields[0]),
        ):
            _, data, _, _, _ = owner_register_optimized.execute_owner_register({})

        self.assertEqual([row["number_of_pets"] for row in data], [2, 1])

    def test_empty_branch_owner_set_skips_pet_and_invoice_aggregates(self):
        aggregate_calls = []

        def get_all(doctype, filters=None, fields=None, order_by=None, group_by=None, pluck=None, **_kwargs):
            if doctype == "Veterinary Patient" and pluck == "primary_owner":
                return []
            if doctype == "Customer":
                return [
                    frappe._dict(name="CUST-001", customer_name="Jane Owner"),
                    frappe._dict(name="CUST-002", customer_name="John Owner"),
                ]
            if doctype in {"Veterinary Patient", "Sales Invoice"}:
                aggregate_calls.append((doctype, filters, group_by))
            return []

        with (
            patch.object(owner_register_optimized.frappe, "get_all", side_effect=get_all),
            patch.object(
                owner_register_optimized.frappe.db,
                "exists",
                side_effect=lambda doctype, name=None: doctype == "DocType" and name == "Veterinary Patient",
            ),
            patch.object(owner_register_optimized, "_existing_field", side_effect=lambda _doctype, fields: fields[0]),
        ):
            _, data, _, _, _ = owner_register_optimized.execute_owner_register({"branch": "Main"})

        self.assertEqual(data, [])
        self.assertEqual(aggregate_calls, [])

    def test_reporting_v3_owner_register_uses_optimized_service(self):
        sentinel = ([{"fieldname": "owner"}], [{"owner": "CUST-001"}], None, None, [])
        with (
            patch.object(reporting_logic_v3, "execute_owner_register", return_value=sentinel) as optimized,
            patch.object(reporting_logic_v3, "_base_execute_structured_report") as legacy,
        ):
            result = reporting_logic_v3._execute_base_report("Owner Register", {"owner": "CUST-001"})

        self.assertEqual(result, sentinel)
        optimized.assert_called_once_with({"owner": "CUST-001"})
        legacy.assert_not_called()

    def test_reporting_v3_non_owner_report_still_delegates_to_existing_base(self):
        sentinel = ([], [], None, None, [])
        with (
            patch.object(reporting_logic_v3, "execute_owner_register") as optimized,
            patch.object(reporting_logic_v3, "_base_execute_structured_report", return_value=sentinel) as legacy,
        ):
            result = reporting_logic_v3._execute_base_report("Patient Register", {"branch": "Main"})

        self.assertEqual(result, sentinel)
        optimized.assert_not_called()
        legacy.assert_called_once_with("Patient Register", {"branch": "Main"})


if __name__ == "__main__":
    unittest.main()
