from __future__ import annotations

import pytest

from vetedge.services.regulatory_report_state import assert_sendable, assert_transition


def test_only_generated_report_is_sendable():
    assert_sendable("Generated")
    for status in ("Sent", "Rejected", "Accepted", "Superseded"):
        with pytest.raises(ValueError):
            assert_sendable(status)


def test_sent_report_can_be_accepted_or_rejected():
    assert_transition("Sent", "Accepted", has_sent_evidence=True)
    assert_transition("Sent", "Rejected", has_sent_evidence=True)


def test_sent_report_cannot_be_sent_again():
    with pytest.raises(ValueError):
        assert_transition("Sent", "Sent", has_sent_evidence=True)
    with pytest.raises(ValueError):
        assert_sendable("Sent")


def test_rejected_report_must_not_be_resent_or_accepted():
    with pytest.raises(ValueError):
        assert_transition("Rejected", "Sent", has_sent_evidence=True)
    with pytest.raises(ValueError):
        assert_transition("Rejected", "Accepted", has_sent_evidence=True)


def test_rejected_report_can_be_superseded_after_correction_workflow():
    assert_transition("Rejected", "Superseded", has_sent_evidence=True)


@pytest.mark.parametrize("final_status", ["Accepted", "Superseded"])
def test_final_statuses_are_immutable(final_status):
    for target in ("Generated", "Sent", "Accepted", "Rejected", "Superseded"):
        if target == final_status:
            assert_transition(final_status, target, has_sent_evidence=True)
            continue
        with pytest.raises(ValueError):
            assert_transition(final_status, target, has_sent_evidence=True)


def test_sent_transition_requires_email_evidence():
    with pytest.raises(ValueError):
        assert_transition("Generated", "Sent", has_sent_evidence=False)
    assert_transition("Generated", "Sent", has_sent_evidence=True)
