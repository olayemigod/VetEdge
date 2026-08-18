from __future__ import annotations

import frappe


FIELDNAME = "allow_vaccination_billing_edit_in_consultation"


def execute() -> None:
    if not frappe.db.exists("DocType", "Veterinary Settings"):
        return
    if frappe.get_meta("Veterinary Settings").has_field(FIELDNAME):
        return

    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {
            "Veterinary Settings": [
                {
                    "fieldname": FIELDNAME,
                    "label": "Allow Vaccination Rate Edits in Consultation",
                    "fieldtype": "Check",
                    "default": "1",
                    "insert_after": "vaccination_requires_payment_before_administration",
                    "description": (
                        "Allow the Rate of a consultation-linked Vaccination treatment row to be edited "
                        "while billing is still unsubmitted. The ERPNext Item remains fixed by the Vaccine "
                        "master so accounting and stock identity stay authoritative."
                    ),
                }
            ]
        },
        update=True,
    )
