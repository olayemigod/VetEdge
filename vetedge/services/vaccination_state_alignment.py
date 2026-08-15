from __future__ import annotations


PRE_ADMIN_STATUSES = {"Draft", "Awaiting Payment", "Pending Administration"}


def align_vaccination_administration_metadata(doc, method: str | None = None) -> None:
    """Administration metadata is produced by the administration workflow only.

    Draft/payment-pending records must not carry an administering user or time,
    even when a client submits stale/hidden values. Cancelled administered records
    retain their historical metadata for auditability.
    """
    if str(doc.get("status") or "Draft") in PRE_ADMIN_STATUSES:
        doc.administered_by = None
        doc.administered_on = None
