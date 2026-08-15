from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cstr

from vetedge.services.portal_access import require_internal_user


INLINE_MASTER_CONFIG = {
    "Customer": {
        "label_field": "customer_name",
        "kind": "owner",
    },
    "Veterinary Species": {
        "label_field": "species_name",
        "kind": "species",
    },
    "Veterinary Breed": {
        "label_field": "breed_name",
        "kind": "breed",
    },
}


def _clean(value: Any) -> str:
    return cstr(value or "").strip()


def _parse(value: str | dict | None) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    parsed = frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected a JSON object."), frappe.ValidationError)
    return parsed


def _config(doctype: str) -> dict[str, str]:
    config = INLINE_MASTER_CONFIG.get(_clean(doctype))
    if not config:
        frappe.throw(_("This linked master is not approved for inline creation."), frappe.PermissionError)
    return config


def _option(doc, config: dict[str, str]) -> dict[str, Any]:
    label = _clean(doc.get(config["label_field"])) or doc.name
    description = ""
    if doc.doctype == "Customer":
        description = " · ".join(filter(None, [_clean(doc.get("mobile_no")), _clean(doc.get("email_id"))]))
    elif doc.doctype == "Veterinary Breed":
        description = _clean(doc.get("species"))
    return {"value": doc.name, "label": label, "description": description}


@frappe.whitelist()
def get_inline_master_capability(doctype: str) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    return {
        "doctype": doctype,
        "kind": config["kind"],
        "can_create": bool(frappe.has_permission(doctype, "create")),
    }


@frappe.whitelist()
def create_inline_master(
    doctype: str,
    label: str = "",
    context: str | dict | None = None,
    values: str | dict | None = None,
) -> dict[str, Any]:
    require_internal_user()
    config = _config(doctype)
    if not frappe.has_permission(doctype, "create"):
        frappe.throw(_("You are not permitted to create {0}.").format(doctype), frappe.PermissionError)

    label = _clean(label)
    ctx = _parse(context)
    payload = _parse(values)

    if doctype == "Customer":
        from vetedge.services.appointment_edgeui import create_appointment_owner

        owner_values = {
            "owner_name": _clean(payload.get("owner_name") or payload.get("customer_name") or label),
            "mobile_no": _clean(payload.get("mobile_no")),
            "email_id": _clean(payload.get("email_id")).lower(),
        }
        return create_appointment_owner(owner_values)

    if doctype == "Veterinary Species":
        species_name = _clean(payload.get("species_name") or label)
        if not species_name:
            frappe.throw(_("Species Name is required."), frappe.ValidationError)
        existing = frappe.db.get_value("Veterinary Species", {"species_name": species_name}, "name")
        if existing:
            doc = frappe.get_doc("Veterinary Species", existing)
            return _option(doc, config)
        doc = frappe.get_doc(
            {
                "doctype": "Veterinary Species",
                "species_name": species_name,
                "description": _clean(payload.get("description")),
                "disabled": 0,
            }
        )
        doc.insert()
        return _option(doc, config)

    species = _clean(payload.get("species") or ctx.get("species"))
    breed_name = _clean(payload.get("breed_name") or label)
    if not species:
        frappe.throw(_("Select Species before creating a Breed."), frappe.ValidationError)
    if not frappe.db.exists("Veterinary Species", species):
        frappe.throw(_("The selected Species is not valid."), frappe.ValidationError)
    if not breed_name:
        frappe.throw(_("Breed Name is required."), frappe.ValidationError)
    existing = frappe.db.get_value(
        "Veterinary Breed", {"species": species, "breed_name": breed_name}, "name"
    )
    if existing:
        doc = frappe.get_doc("Veterinary Breed", existing)
        return _option(doc, config)
    doc = frappe.get_doc(
        {
            "doctype": "Veterinary Breed",
            "breed_name": breed_name,
            "species": species,
            "description": _clean(payload.get("description")),
            "disabled": 0,
        }
    )
    doc.insert()
    return _option(doc, config)
