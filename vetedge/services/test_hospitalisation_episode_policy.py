from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation_episode_policy as policy


def hospitalisation_doc(**values):
    defaults = {
        "doctype": "Veterinary Hospitalisation",
        "name": "VHOS-001",
        "status": "Under Care",
        "charge_items": [],
        "activities": [],
    }
    defaults.update(values)
    doc = frappe._dict(defaults)
    doc.save = Mock()
    return doc


class TestHospitalisationEpisodePolicy(TestCase):
    def test_daily_charge_policy_returns_disabled_result_without_core_call(self):
        with (
            patch.object(policy, "is_hospitalisation_daily_charges_enabled", return_value=False),
            patch(
                "vetedge.services.hospitalisation.generate_hospitalisation_daily_charges"
            ) as core_generate,
        ):
            result = policy.generate_hospitalisation_daily_charges(
                "VHOS-001",
                from_date="2026-08-27",
                to_date="2026-08-27",
            )

        self.assertTrue(result["disabled"])
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["total_amount"], 0)
        self.assertIn("disabled", result["message"].lower())
        core_generate.assert_not_called()

    def test_stock_preview_is_disabled_when_dispensary_flow_is_off(self):
        with patch.object(policy, "is_hospitalisation_dispensary_enabled", return_value=False):
            result = policy.get_hospitalisation_stock_posting_preview("VHOS-001")

        self.assertTrue(result["disabled"])
        self.assertFalse(result["can_post"])
        self.assertEqual(result["to_post_count"], 0)
        self.assertEqual(result["items"], [])
        self.assertTrue(result["warnings"])

    def test_stock_post_is_rejected_when_dispensary_flow_is_off(self):
        with patch.object(policy, "is_hospitalisation_dispensary_enabled", return_value=False):
            with self.assertRaises(frappe.ValidationError):
                policy.post_hospitalisation_activity_stock("VHOS-001")

    def test_billable_medication_and_fluid_therapy_require_an_erpnext_item(self):
        cases = (
            {"activity_type": "Nursing Note", "billable": 1},
            {"activity_type": "Medication"},
            {"activity_type": "Fluid Therapy"},
        )
        for values in cases:
            with self.subTest(values=values):
                with (
                    patch.object(policy, "is_hospitalisation_dispensary_enabled", return_value=True),
                    patch(
                        "vetedge.services.hospitalisation_episode.add_hospitalisation_activity"
                    ) as original,
                ):
                    with self.assertRaises(frappe.ValidationError):
                        policy.add_hospitalisation_activity(
                            "VHOS-001",
                            clinical_notes="Policy contract",
                            **values,
                        )
                    original.assert_not_called()

    def test_stock_flags_are_removed_when_dispensary_flow_is_off(self):
        with (
            patch.object(policy, "is_hospitalisation_dispensary_enabled", return_value=False),
            patch(
                "vetedge.services.hospitalisation_episode.add_hospitalisation_activity",
                return_value={"episode": {}, "warnings": []},
            ) as original,
        ):
            result = policy.add_hospitalisation_activity(
                "VHOS-001",
                activity_type="Medication",
                item="ITEM-001",
                qty=1,
                stock_affecting=1,
                source_warehouse="Main Dispensary - C",
            )

        kwargs = original.call_args.kwargs
        self.assertEqual(kwargs["stock_affecting"], 0)
        self.assertIsNone(kwargs["source_warehouse"])
        self.assertTrue(
            any("Dispensary Flow is disabled" in message for message in result["warnings"])
        )

    def test_submitted_invoice_charge_is_read_only_and_hospitalisation_is_not_saved(self):
        charge = frappe._dict(
            name="CHG-001",
            sales_invoice="SINV-001",
            charge_category="Medication",
            activity_type="Medication",
            item="ITEM-001",
            qty=1,
            uom="Nos",
            rate=500,
        )
        doc = hospitalisation_doc(charge_items=[charge])

        with (
            patch.object(policy, "is_hospitalisation_charge_editing_enabled", return_value=True),
            patch.object(policy, "_load_hospitalisation", return_value=doc),
            patch.object(
                policy,
                "_invoice_state",
                return_value=frappe._dict(
                    docstatus=1,
                    status="Unpaid",
                    outstanding_amount=500,
                ),
            ),
            patch.object(policy.frappe, "has_permission", return_value=True),
        ):
            with self.assertRaises(frappe.ValidationError):
                policy.update_hospitalisation_charge_item(
                    "VHOS-001",
                    "CHG-001",
                    values={"rate": 750},
                )

        doc.save.assert_not_called()

    def test_daily_stay_charge_only_allows_quantity_and_rate_edits(self):
        doc = hospitalisation_doc()
        row = frappe._dict(
            name="CHG-DAILY",
            charge_category="Daily Stay",
            activity_type="Daily Stay",
            sales_invoice=None,
        )

        with (
            patch.object(policy, "is_hospitalisation_charge_editing_enabled", return_value=True),
            patch.object(policy.frappe, "has_permission", return_value=True),
        ):
            editable, fields, reason = policy._charge_editability(doc, row)

        self.assertTrue(editable)
        self.assertEqual(fields, ["qty", "rate"])
        self.assertEqual(reason, "")

    def test_activity_charge_allows_full_draft_charge_fields(self):
        doc = hospitalisation_doc()
        row = frappe._dict(
            name="CHG-ACTIVITY",
            charge_category="Activity",
            activity_type="Medication",
            sales_invoice=None,
        )

        with (
            patch.object(policy, "is_hospitalisation_charge_editing_enabled", return_value=True),
            patch.object(policy.frappe, "has_permission", return_value=True),
        ):
            editable, fields, reason = policy._charge_editability(doc, row)

        self.assertTrue(editable)
        self.assertEqual(fields, ["item", "qty", "uom", "rate", "description"])
        self.assertEqual(reason, "")

    def test_episode_capabilities_follow_daily_charge_and_dispensary_settings(self):
        doc = hospitalisation_doc()
        payload = {
            "name": "VHOS-001",
            "capabilities": {
                "can_write": True,
                "can_post_stock": True,
                "can_manage_charges": True,
            },
            "signals": {"pending_stock": 4},
            "charge_items": [],
        }

        with (
            patch.object(policy, "_load_hospitalisation", return_value=doc),
            patch.object(policy, "is_hospitalisation_dispensary_enabled", return_value=False),
            patch.object(policy, "is_hospitalisation_daily_charges_enabled", return_value=False),
            patch.object(policy, "is_hospitalisation_charge_editing_enabled", return_value=True),
        ):
            result = policy._enrich_episode(payload)

        self.assertFalse(result["capabilities"]["dispensary_enabled"])
        self.assertFalse(result["capabilities"]["can_preview_stock"])
        self.assertFalse(result["capabilities"]["can_post_stock"])
        self.assertFalse(result["capabilities"]["daily_charges_enabled"])
        self.assertFalse(result["capabilities"]["can_generate_daily_charges"])
        self.assertEqual(result["signals"]["pending_stock"], 0)

    def test_day_one_initial_billing_is_blocked_when_daily_charges_are_disabled(self):
        settings = frappe._dict(
            hospitalisation_initial_billing_source="Day 1 Daily Charge"
        )
        with (
            patch.object(policy, "is_hospitalisation_daily_charges_enabled", return_value=False),
            patch.object(policy.frappe.db, "exists", return_value=True),
            patch.object(policy.frappe, "get_single", return_value=settings),
            patch("vetedge.services.hospitalisation.admit_hospitalisation") as core_admit,
        ):
            result = policy.admit_hospitalisation("VHOS-001")

        self.assertTrue(result["blocked"])
        self.assertFalse(result["can_proceed"])
        self.assertIn("Daily Charges are disabled", result["message"])
        core_admit.assert_not_called()

    def test_dispensary_off_normalizes_unposted_stock_before_discharge_readiness(self):
        activity = frappe._dict(
            name="ACT-001",
            stock_affecting=1,
            stock_status="Pending",
            stock_entry=None,
            source_warehouse="Main Dispensary - C",
        )
        doc = hospitalisation_doc(activities=[activity])

        with (
            patch.object(policy, "is_hospitalisation_dispensary_enabled", return_value=False),
            patch.object(policy, "_load_hospitalisation", return_value=doc),
            patch(
                "vetedge.services.hospitalisation.get_hospitalisation_discharge_readiness",
                return_value={"can_discharge": True},
            ) as core_readiness,
        ):
            result = policy.get_hospitalisation_discharge_readiness("VHOS-001")

        self.assertTrue(result["can_discharge"])
        self.assertEqual(activity.stock_affecting, 0)
        self.assertEqual(activity.stock_status, "Not Applicable")
        self.assertIsNone(activity.source_warehouse)
        self.assertIn("Dispensary Flow is disabled", activity.stock_posting_message)
        doc.save.assert_called_once()
        core_readiness.assert_called_once_with("VHOS-001")
