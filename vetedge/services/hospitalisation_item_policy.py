from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services import hospitalisation_episode_policy as base_policy


ITEM_DOCTYPE = "Item"


def _clean(value) -> str:
    return cstr(value or "").strip()


def _item_state(item: str) -> dict:
    if not item:
        return {}
    return frappe.db.get_value(
        ITEM_DOCTYPE,
        item,
        ["name", "item_name", "disabled", "is_sales_item", "is_stock_item", "stock_uom"],
        as_dict=True,
    ) or {}


def _validate_activity_item(item: str | None, *, billable: bool, stock_affecting: bool) -> None:
    if not item:
        return
    state = _item_state(item)
    if not state or cint(state.get("disabled")):
        frappe.throw(_("Select an enabled ERPNext Item."), frappe.ValidationError)
    if billable and not cint(state.get("is_sales_item")):
        frappe.throw(
            _("Billable Hospitalisation activities require an Item enabled for Sales."),
            frappe.ValidationError,
        )
    if stock_affecting and not cint(state.get("is_stock_item")):
        frappe.throw(
            _("Stock-affecting Hospitalisation activities require a Stock Item."),
            frappe.ValidationError,
        )


@frappe.whitelist()
def add_hospitalisation_activity(
    hospitalisation_name: str,
    activity_type: str,
    activity_datetime: str | None = None,
    clinical_notes: str | None = None,
    billable: int | str = 0,
    stock_affecting: int | str = 0,
    item: str | None = None,
    qty: float | str | None = None,
    uom: str | None = None,
    source_warehouse: str | None = None,
    modified: str | None = None,
) -> dict:
    resolved_item = _clean(item) or None
    _validate_activity_item(
        resolved_item,
        billable=bool(cint(billable)),
        stock_affecting=bool(cint(stock_affecting) and base_policy.is_hospitalisation_dispensary_enabled()),
    )
    return base_policy.add_hospitalisation_activity(
        hospitalisation_name=hospitalisation_name,
        activity_type=activity_type,
        activity_datetime=activity_datetime,
        clinical_notes=clinical_notes,
        billable=billable,
        stock_affecting=stock_affecting,
        item=resolved_item,
        qty=qty,
        uom=uom,
        source_warehouse=source_warehouse,
        modified=modified,
    )


@frappe.whitelist()
def search_hospitalisation_episode_options(
    hospitalisation_name: str,
    field: str,
    txt: str = "",
    start: int | str = 0,
    page_length: int | str = 20,
):
    if field != "item":
        from vetedge.services.hospitalisation_episode import search_hospitalisation_episode_options as original

        return original(
            hospitalisation_name=hospitalisation_name,
            field=field,
            txt=txt,
            start=start,
            page_length=page_length,
        )

    # Resolve Hospitalisation access first; the picker itself must remain branch
    # and permission aware even though Item is a shared ERPNext master.
    base_policy._load_hospitalisation(hospitalisation_name)
    query = _clean(txt)
    try:
        offset = max(int(start or 0), 0)
    except (TypeError, ValueError):
        offset = 0
    try:
        limit = min(max(int(page_length or 20), 1), 50)
    except (TypeError, ValueError):
        limit = 20

    filters = {"disabled": 0, "is_sales_item": 1}
    or_filters = None
    if query:
        or_filters = [
            [ITEM_DOCTYPE, "name", "like", f"%{query}%"],
            [ITEM_DOCTYPE, "item_name", "like", f"%{query}%"],
        ]
    rows = frappe.get_list(
        ITEM_DOCTYPE,
        filters=filters,
        or_filters=or_filters,
        fields=["name", "item_name", "stock_uom", "is_stock_item"],
        order_by="item_name asc",
        start=offset,
        page_length=limit,
    )
    return [
        {
            "value": row.get("name"),
            "label": row.get("item_name") or row.get("name"),
            "description": " · ".join(
                filter(None, [row.get("stock_uom"), "Stock Item" if cint(row.get("is_stock_item")) else "Service Item"])
            ),
            "uom": row.get("stock_uom"),
            "is_stock_item": cint(row.get("is_stock_item")),
        }
        for row in rows
    ]
