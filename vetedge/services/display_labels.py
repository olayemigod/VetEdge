from __future__ import annotations

from collections import defaultdict

import frappe


TITLE_FIELDS = {
    "Veterinary Patient": "patient_name",
    "Customer": "customer_name",
    "Veterinary Species": "species_name",
    "Veterinary Breed": "breed_name",
    "Veterinary Vaccine": "vaccine_name",
    "Veterinary Lab Test": "test_name",
    "Item": "item_name",
    "User": "full_name",
}

# These document numbers are the meaningful business references and must not be
# replaced by the linked document's title field (for example Sales Invoice's
# customer title).
REFERENCE_NAME_DOCTYPES = {
    "Sales Invoice",
    "Payment Entry",
    "Stock Entry",
    "Veterinary Consultation",
    "Veterinary Appointment",
    "Veterinary Lab Order",
    "Veterinary Vaccination Record",
    "Veterinary Vital Signs",
}


def get_display_label(doctype: str | None, name: str | None) -> str:
    doctype = str(doctype or "").strip()
    name = str(name or "").strip()
    if not doctype or not name:
        return name
    if doctype in REFERENCE_NAME_DOCTYPES:
        return name
    fieldname = TITLE_FIELDS.get(doctype)
    if fieldname:
        return frappe.db.get_value(doctype, name, fieldname) or name
    try:
        meta = frappe.get_meta(doctype)
        title_field = meta.get_title_field()
        if title_field and title_field != "name":
            return frappe.db.get_value(doctype, name, title_field) or name
    except Exception:
        pass
    return name


def enrich_link_display_values(rows: list, columns: list[dict], replace_values: bool = True) -> None:
    """Resolve Link labels for presentation rows while preserving raw Link IDs.

    `_display` remains available to modern renderers. `replace_values=True` also
    places the readable label into the visible field itself for older/current
    EdgeSuite table components that render the raw row value directly. The
    authoritative database Link value is retained in `_raw` and is never used
    to mutate source documents from these read-only list payloads.
    """
    link_columns = [column for column in columns or [] if column.get("fieldtype") == "Link"]
    if not rows or not link_columns:
        return

    values_by_doctype: dict[str, set[str]] = defaultdict(set)
    field_doctypes: dict[str, str] = {}
    for column in link_columns:
        doctype = str(column.get("options") or "").strip()
        fieldname = str(column.get("fieldname") or "").strip()
        if not doctype or not fieldname:
            continue
        field_doctypes[fieldname] = doctype
        for row in rows:
            value = str(row.get(fieldname) or "").strip()
            if value:
                values_by_doctype[doctype].add(value)

    caches: dict[str, dict[str, str]] = {}
    for doctype, names in values_by_doctype.items():
        if doctype in REFERENCE_NAME_DOCTYPES:
            caches[doctype] = {name: name for name in names}
            continue
        title_field = TITLE_FIELDS.get(doctype)
        if not title_field:
            try:
                title_field = frappe.get_meta(doctype).get_title_field()
            except Exception:
                title_field = None
        if not title_field or title_field == "name":
            caches[doctype] = {name: name for name in names}
            continue
        result = frappe.get_list(
            doctype,
            filters={"name": ["in", list(names)]},
            fields=["name", title_field],
            page_length=max(len(names), 1),
        )
        caches[doctype] = {
            row.name: str(row.get(title_field) or row.name) for row in result
        }

    for row in rows:
        display = row.setdefault("_display", {})
        raw = row.setdefault("_raw", {}) if replace_values else None
        for fieldname, doctype in field_doctypes.items():
            value = str(row.get(fieldname) or "").strip()
            if not value:
                continue
            label = caches.get(doctype, {}).get(value, value)
            display[fieldname] = label
            if replace_values and label != value:
                raw[fieldname] = value
                row[fieldname] = label
        if replace_values and raw is not None and not raw:
            row.pop("_raw", None)
