from __future__ import annotations

import frappe


SETTINGS_DOCTYPE = "Veterinary Settings"
DAILY_CHARGE_FIELD = "hospitalisation_daily_charge_settings"
DAILY_CHARGE_DEPENDS_ON = (
    "eval:doc.enable_veterinary_hospitalisation && doc.enable_hospitalisation_daily_charges"
)


def execute() -> None:
    """Keep Hospitalisation daily-charge configuration subordinate to its clinic switch.

    The switch itself is introduced by the preceding Hospitalisation Episode
    settings patch. A Property Setter is used here because the switch is a
    Custom Field on existing VetEdge sites while the daily-charge child table is
    a standard Veterinary Settings field.
    """
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        return

    meta = frappe.get_meta(SETTINGS_DOCTYPE)
    if not meta.has_field("enable_hospitalisation_daily_charges") or not meta.has_field(DAILY_CHARGE_FIELD):
        return

    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    make_property_setter(
        SETTINGS_DOCTYPE,
        DAILY_CHARGE_FIELD,
        "depends_on",
        DAILY_CHARGE_DEPENDS_ON,
        "Data",
    )
