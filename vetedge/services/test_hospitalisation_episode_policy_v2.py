from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation_episode_policy_v2 as policy


class TestHospitalisationEpisodePolicyV2(TestCase):
    def test_disabled_stock_preview_still_requires_hospitalisation_access(self):
        doc = frappe._dict(name="VHOS-001")
        with (
            patch.object(policy, "_require_hospitalisation_access", return_value=doc) as require_access,
            patch.object(policy.base_policy, "is_hospitalisation_dispensary_enabled", return_value=False),
        ):
            result = policy.get_hospitalisation_stock_posting_preview("VHOS-001")

        require_access.assert_called_once_with("VHOS-001")
        self.assertTrue(result["disabled"])
        self.assertFalse(result["can_post"])

    def test_disabled_daily_charges_still_require_write_access(self):
        doc = frappe._dict(name="VHOS-001")
        with (
            patch.object(policy, "_require_hospitalisation_access", return_value=doc) as require_access,
            patch.object(policy.base_policy, "is_hospitalisation_daily_charges_enabled", return_value=False),
        ):
            result = policy.generate_hospitalisation_daily_charges("VHOS-001")

        require_access.assert_called_once_with("VHOS-001", write=True)
        self.assertTrue(result["disabled"])

    def test_readiness_ignores_disabled_stock_without_mutating_activity(self):
        activity = frappe._dict(
            name="ACT-001",
            stock_affecting=1,
            stock_status="Pending",
            source_warehouse="Dispensary - C",
        )
        doc = frappe._dict(
            name="VHOS-001",
            discharge_summary="Stable for discharge",
            activities=[activity],
        )
        doc.save = Mock()
        readiness = {
            "pending_billable_activities": [],
            "pending_charge_items": [],
            "pending_stock_activities": [{"activity": "ACT-001"}],
            "payment_gate": {"can_proceed": True},
            "messages": ["There are stock-affecting activities that have not been posted."],
            "warnings": ["There are stock-affecting activities that have not been posted."],
            "recommended_actions": ["Post Stock Usage"],
            "can_discharge": False,
            "discharge_billing_status": "Cleared",
        }
        with (
            patch.object(policy, "_require_hospitalisation_access", return_value=doc),
            patch.object(policy.base_policy, "is_hospitalisation_dispensary_enabled", return_value=False),
            patch(
                "vetedge.services.hospitalisation.build_hospitalisation_discharge_readiness",
                return_value=readiness,
            ),
        ):
            result = policy.get_hospitalisation_discharge_readiness("VHOS-001")

        self.assertEqual(result["pending_stock_activities"], [])
        self.assertTrue(result["can_discharge"])
        self.assertEqual(activity.stock_affecting, 1)
        self.assertEqual(activity.stock_status, "Pending")
        self.assertEqual(activity.source_warehouse, "Dispensary - C")
        doc.save.assert_not_called()

    def test_timeline_activity_for_dedicated_clinical_record_is_not_billable_or_stock_affecting(self):
        appended = {}
        row = frappe._dict(name="ACT-001")
        doc = frappe._dict(name="VHOS-001")
        doc.save = Mock()
        episode = Mock()
        episode._assert_open_episode = Mock()

        def append_activity(_doc, values):
            appended.update(values)
            return row

        episode._append_activity = append_activity
        with patch.object(policy, "_episode_module", return_value=episode):
            result = policy._append_linked_timeline_activity(
                doc,
                activity_type="Vaccination",
                clinical_notes="Rabies vaccine",
                linked_doctype="Veterinary Vaccination Record",
                linked_document="VAX-001",
                item="RABIES-VAX",
                qty=1,
            )

        self.assertIs(result, row)
        self.assertEqual(appended["billable"], 0)
        self.assertEqual(appended["stock_affecting"], 0)
        self.assertEqual(appended["linked_document"], "VAX-001")
        doc.save.assert_called_once()
