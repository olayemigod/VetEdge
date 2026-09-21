from __future__ import annotations

import unittest

from vetedge.services.regulatory_report_state import assert_sendable, assert_transition


class TestRegulatoryReportState(unittest.TestCase):
    def test_only_generated_report_is_sendable(self):
        assert_sendable("Generated")
        for status in ("Sent", "Rejected", "Accepted", "Superseded"):
            with self.assertRaises(ValueError):
                assert_sendable(status)

    def test_sent_report_can_be_accepted_or_rejected(self):
        assert_transition("Sent", "Accepted", has_sent_evidence=True)
        assert_transition("Sent", "Rejected", has_sent_evidence=True)

    def test_sent_report_cannot_be_emailed_again(self):
        with self.assertRaises(ValueError):
            assert_sendable("Sent")

    def test_rejected_report_must_not_be_resent_or_accepted(self):
        with self.assertRaises(ValueError):
            assert_transition("Rejected", "Sent", has_sent_evidence=True)
        with self.assertRaises(ValueError):
            assert_transition("Rejected", "Accepted", has_sent_evidence=True)

    def test_rejected_report_can_be_superseded_after_correction_workflow(self):
        assert_transition("Rejected", "Superseded", has_sent_evidence=True)

    def test_final_statuses_are_immutable(self):
        for final_status in ("Accepted", "Superseded"):
            for target in ("Generated", "Sent", "Accepted", "Rejected", "Superseded"):
                if target == final_status:
                    assert_transition(final_status, target, has_sent_evidence=True)
                    continue
                with self.assertRaises(ValueError):
                    assert_transition(final_status, target, has_sent_evidence=True)

    def test_sent_transition_requires_email_evidence(self):
        with self.assertRaises(ValueError):
            assert_transition("Generated", "Sent", has_sent_evidence=False)
        assert_transition("Generated", "Sent", has_sent_evidence=True)
