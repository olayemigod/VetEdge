from __future__ import annotations

SENDABLE_STATUSES = {"Generated", "Sent"}
FINAL_STATUSES = {"Accepted", "Superseded"}
ALLOWED_STATUSES = {"Generated", "Sent", "Accepted", "Rejected", "Superseded"}


def assert_sendable(current_status: str) -> None:
    if current_status not in SENDABLE_STATUSES:
        raise ValueError(
            "Only Generated or Sent regulatory reports can be emailed. "
            "Rejected reports must be corrected, regenerated, and then marked Superseded."
        )


def assert_transition(current_status: str, target_status: str, *, has_sent_evidence: bool = False) -> None:
    if target_status not in ALLOWED_STATUSES:
        raise ValueError("Unsupported regulatory submission status.")

    if current_status in FINAL_STATUSES and target_status != current_status:
        raise ValueError(f"A regulatory report marked {current_status} cannot be moved to another status.")

    if target_status == current_status:
        return

    if target_status == "Generated":
        raise ValueError("A submitted regulatory report cannot be reset to Generated.")

    if target_status == "Sent":
        if current_status not in SENDABLE_STATUSES:
            raise ValueError(
                "A Rejected, Accepted, or Superseded regulatory report cannot be moved to Sent."
            )
        if not has_sent_evidence:
            raise ValueError("Sent status requires Sent To and Sent On evidence.")
        return

    if target_status in {"Accepted", "Rejected"}:
        if current_status != "Sent":
            raise ValueError("Only a Sent regulatory report can be marked Accepted or Rejected.")
        return

    if target_status == "Superseded":
        if current_status == "Accepted":
            raise ValueError("An Accepted regulatory report is final and cannot be superseded.")
        return
