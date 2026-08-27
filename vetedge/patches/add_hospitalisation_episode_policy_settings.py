from __future__ import annotations

import frappe


SETTINGS_DOCTYPE = "Veterinary Settings"


def execute() -> None:
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        return

    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {
            SETTINGS_DOCTYPE: [
                {
                    "fieldname": "enable_hospitalisation_daily_charges",
                    "label": "Enable Hospitalisation Daily Charges",
                    "fieldtype": "Check",
                    "default": "1",
                    "insert_after": "hospitalisation_admission_fee_uom",
                    "depends_on": "eval:doc.enable_veterinary_hospitalisation",
                    "description": (
                        "Enable daily-stay charge generation for Hospitalisation. Disable this when the clinic "
                        "does not charge patients per hospitalisation day."
                    ),
                },
                {
                    "fieldname": "allow_editing_hospitalisation_charge_items",
                    "label": "Allow Editing Hospitalisation Charge Items",
                    "fieldtype": "Check",
                    "default": "1",
                    "insert_after": "enable_hospitalisation_daily_charges",
                    "depends_on": "eval:doc.enable_veterinary_hospitalisation",
                    "description": (
                        "Allow Item, Quantity, UOM and Rate edits while the related Sales Invoice is still "
                        "draft or the charge has not yet been invoiced. Submitted accounting documents remain immutable."
                    ),
                },
            ],
            "Veterinary Vital Signs": [
                {
                    "fieldname": "hospitalisation",
                    "label": "Hospitalisation",
                    "fieldtype": "Link",
                    "options": "Veterinary Hospitalisation",
                    "insert_after": "consultation",
                    "read_only": 1,
                    "no_copy": 1,
                    "description": "Hospitalisation episode that created this clinical record, when applicable.",
                }
            ],
            "Veterinary Vaccination Record": [
                {
                    "fieldname": "hospitalisation",
                    "label": "Hospitalisation",
                    "fieldtype": "Link",
                    "options": "Veterinary Hospitalisation",
                    "insert_after": "linked_consultation",
                    "read_only": 1,
                    "no_copy": 1,
                    "description": "Hospitalisation episode that created this vaccination record, when applicable.",
                }
            ],
            "Veterinary Lab Order": [
                {
                    "fieldname": "hospitalisation",
                    "label": "Hospitalisation",
                    "fieldtype": "Link",
                    "options": "Veterinary Hospitalisation",
                    "insert_after": "consultation",
                    "read_only": 1,
                    "no_copy": 1,
                    "description": "Hospitalisation episode that created this laboratory order, when applicable.",
                }
            ],
        },
        update=True,
    )
