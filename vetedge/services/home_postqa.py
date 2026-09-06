from __future__ import annotations

import frappe

from vetedge.services import home as home_service
from vetedge.services.display_labels import enrich_link_display_values


@frappe.whitelist()
def get_metric_drilldown(
    metric_key: str,
    operational_date: str | None = None,
    branch: str | None = None,
    limit_start: int = 0,
    limit_page_length: int = home_service.HOME_PAGE_LENGTH,
) -> dict:
    """Return the canonical Home drill-down with readable Link labels.

    The underlying Home service remains authoritative for persona, feature,
    branch, permission, filter, count and pagination rules. This post-QA layer
    only enriches presentation values for Link columns; raw identifiers remain
    in each row's ``_raw`` mapping when a readable label replaces the value.
    """
    result = home_service.get_metric_drilldown(
        metric_key=metric_key,
        operational_date=operational_date,
        branch=branch,
        limit_start=limit_start,
        limit_page_length=limit_page_length,
    )

    doctype = str(result.get("doctype") or "").strip()
    rows = result.get("rows") or []
    columns = result.get("columns") or []
    if not doctype or not rows or not columns:
        return result

    meta = frappe.get_meta(doctype)
    enriched_columns: list[dict] = []
    for column in columns:
        resolved = dict(column)
        fieldname = str(resolved.get("fieldname") or resolved.get("key") or "").strip()
        field = meta.get_field(fieldname) if fieldname and fieldname != "name" else None
        if field:
            resolved["fieldtype"] = resolved.get("fieldtype") or field.fieldtype
            if field.fieldtype == "Link":
                resolved["options"] = field.options or ""
        enriched_columns.append(resolved)

    try:
        enrich_link_display_values(rows, enriched_columns, replace_values=True)
    except frappe.PermissionError:
        # The authoritative drill-down is still safe and useful when a user can
        # read the source record but cannot resolve a linked document's title.
        # In that case preserve the original identifier rather than broadening
        # permissions or bypassing Frappe's permission-aware get_list lookup.
        pass

    result["columns"] = enriched_columns
    return result
