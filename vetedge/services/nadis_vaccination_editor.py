from __future__ import annotations

from typing import Any


FIELDNAME = "vaccination_reason"


def extend_vaccination_editor_config(record_config: dict[str, dict[str, Any]]) -> None:
    """Idempotently expose NADIS vaccination reason in the established editor.

    The field is regulatory classification only. It does not alter billing,
    stock posting, administration metadata or submitted ERPNext documents, so
    it remains safe to correct after invoice submission for historical reports.
    """
    config = record_config.get("Veterinary Vaccination Record")
    if not config:
        return

    fields = list(config.get("fields") or [])
    if not any(fieldname == FIELDNAME for fieldname, _editable in fields):
        dose_index = next((index for index, (fieldname, _editable) in enumerate(fields) if fieldname == "dose"), len(fields))
        fields.insert(dose_index, (FIELDNAME, True))
        config["fields"] = fields

    safe_after_invoice = set(config.get("safe_after_invoice") or set())
    safe_after_invoice.add(FIELDNAME)
    config["safe_after_invoice"] = safe_after_invoice
