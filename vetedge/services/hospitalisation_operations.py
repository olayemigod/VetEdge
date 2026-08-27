from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services.hospitalisation import assert_hospitalisation_enabled
from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters


DOCTYPE = "Veterinary Hospitalisation"
ACTIVITY_DOCTYPE = "Veterinary Hospitalisation Activity"
CHARGE_DOCTYPE = "Veterinary Hospitalisation Charge Item"
PAGE_LENGTH_MAX = 100
OPERATIONAL_ACTIVE_STATUSES = {"Admitted", "Under Care", "Ready for Discharge"}


def _filters(value: str | dict | None) -> dict:
    if not value:
        value = {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected Hospitalisation filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    if cleaned.get("customer") and not cleaned.get("owner"):
        cleaned["owner"] = cleaned.get("customer")
    # Reuse the established Hospitalisation reporting visibility contract for
    # Branch normalization/role checks. The DocType permission hook remains the
    # final authority for each list query.
    return dict(normalize_report_filters("Active Hospitalisations", cleaned) or {})


def _query_filters(filters: dict) -> dict:
    output = {}
    mappings = {
        "branch": "service_branch",
        "status": "status",
        "patient": "patient",
        "owner": "customer",
        "practitioner": "attending_veterinarian",
        "care_level": "care_level",
        "care_location": "care_location",
        "invoice_status": "invoice_status",
        "payment_gate_status": "payment_gate_status",
        "company": "company",
    }
    for source, target in mappings.items():
        if filters.get(source):
            output[target] = filters.get(source)

    if not filters.get("status") and cint(filters.get("active_only", 1)):
        output["status"] = ["in", sorted(OPERATIONAL_ACTIVE_STATUSES)]

    from_date = filters.get("from_date") or filters.get("admission_date_from")
    to_date = filters.get("to_date") or filters.get("admission_date_to")
    if from_date and to_date:
        output["admission_datetime"] = ["between", [from_date, f"{to_date} 23:59:59"]]
    elif from_date:
        output["admission_datetime"] = [">=", from_date]
    elif to_date:
        output["admission_datetime"] = ["<=", f"{to_date} 23:59:59"]
    return output


def _visible_count(query_filters: dict) -> int:
    rows = frappe.get_list(
        DOCTYPE,
        filters=query_filters,
        fields=[{"COUNT": "name", "as": "row_count"}],
        page_length=1,
    )
    return cint(rows[0].get("row_count")) if rows else 0


def _status_counts(query_filters: dict) -> dict[str, int]:
    base = dict(query_filters)
    base.pop("status", None)
    rows = frappe.get_list(
        DOCTYPE,
        filters=base,
        fields=["status", {"COUNT": "name", "as": "row_count"}],
        group_by="status",
        page_length=20,
    )
    return {cstr(row.get("status")): cint(row.get("row_count")) for row in rows}


def _page_rows(query_filters: dict, start: int, page_length: int) -> list[dict]:
    return frappe.get_list(
        DOCTYPE,
        filters=query_filters,
        fields=[
            "name",
            "patient",
            "patient_name",
            "customer",
            "status",
            "admission_datetime",
            "service_branch",
            "company",
            "attending_veterinarian",
            "care_level",
            "care_location",
            "care_location_status",
            "isolation_required",
            "sales_invoice",
            "invoice_status",
            "payment_gate_status",
            "discharge_billing_status",
            "follow_up_date",
            "modified",
        ],
        order_by="admission_datetime desc, name desc",
        start=start,
        page_length=page_length,
    )


def _activity_aggregates(parent_names: list[str]) -> dict[str, dict]:
    result = defaultdict(
        lambda: {
            "activity_count": 0,
            "latest_activity_datetime": None,
            "pending_stock_count": 0,
            "pending_billable_activity_count": 0,
        }
    )
    if not parent_names:
        return result

    # Dispensary Flow is the action authority. Historical stock-affecting rows
    # remain visible in the episode timeline, but they must not surface as
    # actionable "Pending Stock" while the clinic has disabled stock movement.
    from vetedge.services.hospitalisation_episode_policy import is_hospitalisation_dispensary_enabled

    dispensary_enabled = is_hospitalisation_dispensary_enabled()
    rows = frappe.get_all(
        ACTIVITY_DOCTYPE,
        filters={"parent": ["in", parent_names]},
        fields=[
            "parent",
            "activity_datetime",
            "billable",
            "billing_status",
            "stock_affecting",
            "stock_status",
            "stock_entry",
        ],
        order_by="parent asc, activity_datetime desc, idx desc",
    )
    for row in rows:
        item = result[row.get("parent")]
        item["activity_count"] += 1
        activity_datetime = row.get("activity_datetime")
        if activity_datetime and not item["latest_activity_datetime"]:
            item["latest_activity_datetime"] = activity_datetime
        if (
            dispensary_enabled
            and cint(row.get("stock_affecting"))
            and row.get("stock_status") != "Posted"
            and not row.get("stock_entry")
        ):
            item["pending_stock_count"] += 1
        if cint(row.get("billable")) and row.get("billing_status") not in {"Charged", "Cancelled"}:
            item["pending_billable_activity_count"] += 1
    return result


def _charge_aggregates(parent_names: list[str]) -> dict[str, dict]:
    result = defaultdict(
        lambda: {
            "charge_total": 0.0,
            "pending_charge_amount": 0.0,
            "invoiced_charge_amount": 0.0,
            "missing_price_count": 0,
        }
    )
    if not parent_names:
        return result
    rows = frappe.get_all(
        CHARGE_DOCTYPE,
        filters={"parent": ["in", parent_names]},
        fields=["parent", "item", "qty", "rate", "amount", "billing_status"],
        order_by="parent asc, idx asc",
    )
    for row in rows:
        item = result[row.get("parent")]
        qty = flt(row.get("qty")) or 1
        rate = flt(row.get("rate"))
        amount = flt(row.get("amount")) or qty * rate
        if row.get("billing_status") != "Cancelled":
            item["charge_total"] += amount
        if row.get("billing_status") == "Invoiced":
            item["invoiced_charge_amount"] += amount
        elif row.get("billing_status") != "Cancelled":
            item["pending_charge_amount"] += amount
            if row.get("item") and (rate <= 0 or amount <= 0):
                item["missing_price_count"] += 1
    return result


def _summary(query_filters: dict, total: int) -> list[dict]:
    counts = _status_counts(query_filters)
    active = sum(counts.get(status, 0) for status in OPERATIONAL_ACTIVE_STATUSES)
    return [
        {"key": "active", "label": _("Active Hospitalisations"), "value": active, "datatype": "Int"},
        {"key": "ready", "label": _("Ready for Discharge"), "value": counts.get("Ready for Discharge", 0), "datatype": "Int"},
        {"key": "admitted", "label": _("Admitted"), "value": counts.get("Admitted", 0), "datatype": "Int"},
        {"key": "under_care", "label": _("Under Care"), "value": counts.get("Under Care", 0), "datatype": "Int"},
        {"key": "matching", "label": _("Matching Records"), "value": total, "datatype": "Int"},
    ]


def _columns() -> list[dict]:
    return [
        {"fieldname": "hospitalisation", "label": _("Hospitalisation"), "fieldtype": "Link", "options": DOCTYPE},
        {"fieldname": "patient_name", "label": _("Patient"), "fieldtype": "Data"},
        {"fieldname": "owner", "label": _("Pet Owner"), "fieldtype": "Link", "options": "Customer"},
        {"fieldname": "branch", "label": _("Branch"), "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "admission_datetime", "label": _("Admitted On"), "fieldtype": "Datetime"},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
        {"fieldname": "care_level", "label": _("Care Level"), "fieldtype": "Data"},
        {"fieldname": "care_location", "label": _("Care Location"), "fieldtype": "Link", "options": "Veterinary Care Location"},
        {"fieldname": "attending_veterinarian", "label": _("Attending Veterinarian"), "fieldtype": "Link", "options": "User"},
        {"fieldname": "latest_activity_datetime", "label": _("Latest Activity"), "fieldtype": "Datetime"},
        {"fieldname": "pending_stock_count", "label": _("Pending Stock"), "fieldtype": "Int"},
        {"fieldname": "pending_charge_amount", "label": _("Pending Charges"), "fieldtype": "Currency"},
        {"fieldname": "missing_price_count", "label": _("Missing Prices"), "fieldtype": "Int"},
        {"fieldname": "invoice_status", "label": _("Invoice Status"), "fieldtype": "Data"},
        {"fieldname": "payment_gate_status", "label": _("Payment Gate"), "fieldtype": "Data"},
    ]


@frappe.whitelist()
@frappe.read_only()
def get_hospitalisation_operations(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
) -> dict:
    require_internal_user()
    assert_hospitalisation_enabled()
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view Hospitalisations."), frappe.PermissionError)

    report_filters = _filters(filters)
    query_filters = _query_filters(report_filters)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)

    total = _visible_count(query_filters)
    parents = _page_rows(query_filters, start, page_length)
    parent_names = [row.get("name") for row in parents if row.get("name")]
    activities = _activity_aggregates(parent_names)
    charges = _charge_aggregates(parent_names)

    rows = []
    for parent in parents:
        name = parent.get("name")
        activity = activities.get(name) or {}
        charge = charges.get(name) or {}
        rows.append(
            {
                "hospitalisation": name,
                "patient": parent.get("patient"),
                "patient_name": parent.get("patient_name") or parent.get("patient"),
                "owner": parent.get("customer"),
                "branch": parent.get("service_branch"),
                "company": parent.get("company"),
                "admission_datetime": parent.get("admission_datetime"),
                "status": parent.get("status"),
                "care_level": parent.get("care_level"),
                "care_location": parent.get("care_location"),
                "care_location_status": parent.get("care_location_status"),
                "isolation_required": cint(parent.get("isolation_required")),
                "attending_veterinarian": parent.get("attending_veterinarian"),
                "activity_count": cint(activity.get("activity_count")),
                "latest_activity_datetime": activity.get("latest_activity_datetime"),
                "pending_stock_count": cint(activity.get("pending_stock_count")),
                "pending_billable_activity_count": cint(activity.get("pending_billable_activity_count")),
                "charge_total": flt(charge.get("charge_total")),
                "pending_charge_amount": flt(charge.get("pending_charge_amount")),
                "invoiced_charge_amount": flt(charge.get("invoiced_charge_amount")),
                "missing_price_count": cint(charge.get("missing_price_count")),
                "sales_invoice": parent.get("sales_invoice"),
                "invoice_status": parent.get("invoice_status"),
                "payment_gate_status": parent.get("payment_gate_status"),
                "discharge_billing_status": parent.get("discharge_billing_status"),
                "follow_up_date": parent.get("follow_up_date"),
                "modified": parent.get("modified"),
            }
        )

    return {
        "title": _("Hospitalisation Operations"),
        "columns": _columns(),
        "rows": rows,
        "summary": _summary(query_filters, total),
        "total": total,
        "start": start,
        "page_length": page_length,
        "has_previous": start > 0,
        "has_next": start + len(rows) < total,
        "metadata": {
            "pagination_mode": "query-level-parent-page-child-enrichment",
            "all_matching_rows_materialized": False,
            "child_scope": "requested_parent_page_only",
            "max_page_length": PAGE_LENGTH_MAX,
        },
    }
