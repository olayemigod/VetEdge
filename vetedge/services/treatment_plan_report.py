from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_structure import (
    _display_consultation_type,
    _get_consultation_rows,
    _get_patient_title_map,
    _get_user_full_name_map,
)

PAGE_LENGTH_MAX = 100
TREATMENT_FIELDS = [
    "parent",
    "item",
    "qty",
    "uom",
    "rate",
    "amount",
    "service_type",
    "treatment_type",
    "notes",
    "idx",
]


def _filters(value: str | dict | None) -> dict:
    if not value:
        return {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    return dict(normalize_report_filters("Planned Treatment", cleaned) or {})


def _columns() -> list[dict]:
    return [
        {"fieldname": "consultation", "label": _("Consultation"), "fieldtype": "Link", "options": "Veterinary Consultation"},
        {"fieldname": "consultation_date", "label": _("Consultation Date"), "fieldtype": "Datetime"},
        {"fieldname": "service_branch", "label": _("Service Branch"), "fieldtype": "Link", "options": "Branch"},
        {"fieldname": "patient", "label": _("Patient"), "fieldtype": "Data"},
        {"fieldname": "owner", "label": _("Owner"), "fieldtype": "Link", "options": "Customer"},
        {"fieldname": "practitioner", "label": _("Practitioner"), "fieldtype": "Data"},
        {"fieldname": "consultation_type", "label": _("Consultation Type"), "fieldtype": "Link", "options": "Consultation Type"},
        {"fieldname": "item", "label": _("Treatment Item / Service"), "fieldtype": "Link", "options": "Item"},
        {"fieldname": "description", "label": _("Description / Notes"), "fieldtype": "Data"},
        {"fieldname": "qty", "label": _("Quantity"), "fieldtype": "Float"},
        {"fieldname": "uom", "label": _("UOM"), "fieldtype": "Link", "options": "UOM"},
        {"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency"},
        {"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency"},
        {"fieldname": "consultation_total", "label": _("Consultation Total"), "fieldtype": "Currency"},
        {"fieldname": "patient_total", "label": _("Patient Total"), "fieldtype": "Currency"},
        {"fieldname": "status", "label": _("Status"), "fieldtype": "Data"},
    ]


def _patient_owner_map(patient_ids) -> dict[str, str]:
    patient_ids = sorted({cstr(value).strip() for value in patient_ids if cstr(value).strip()})
    if not patient_ids or not frappe.db.exists("DocType", "Veterinary Patient"):
        return {}
    meta = frappe.get_meta("Veterinary Patient")
    owner_field = "primary_owner" if meta.get_field("primary_owner") else ("owner" if meta.get_field("owner") else None)
    if not owner_field:
        return {}
    return {
        row.get("name"): row.get(owner_field)
        for row in frappe.get_all(
            "Veterinary Patient",
            filters={"name": ("in", patient_ids)},
            fields=["name", owner_field],
        )
    }


def _treatment_filters(consultation_names: list[str], report_filters: dict) -> dict:
    filters = {"parent": ("in", consultation_names)}
    if report_filters.get("item"):
        filters["item"] = report_filters.get("item")
    return filters


def _sql_parent_clause(parent_names: list[str], params: dict) -> str:
    placeholders = []
    for index, parent in enumerate(parent_names):
        key = f"parent_{index}"
        params[key] = parent
        placeholders.append(f"%({key})s")
    return ", ".join(placeholders) or "NULL"


def _aggregate_treatments(parent_names: list[str], item: str | None = None, group_by_parent: bool = False):
    parent_names = sorted({cstr(value).strip() for value in parent_names if cstr(value).strip()})
    if not parent_names:
        return [] if group_by_parent else {"total": 0, "grand_total": 0.0}

    params: dict = {}
    parent_clause = _sql_parent_clause(parent_names, params)
    item_clause = ""
    if item:
        params["item"] = item
        item_clause = " AND `item` = %(item)s"
    amount_expression = "CASE WHEN IFNULL(`amount`, 0) != 0 THEN `amount` ELSE IFNULL(`qty`, 0) * IFNULL(`rate`, 0) END"
    select = (
        f"`parent`, COUNT(*) AS `row_count`, SUM({amount_expression}) AS `grand_total`"
        if group_by_parent
        else f"COUNT(*) AS `total`, SUM({amount_expression}) AS `grand_total`"
    )
    group = " GROUP BY `parent`" if group_by_parent else ""
    rows = frappe.db.sql(
        f"SELECT {select} FROM `tabPlanned Treatment Item` WHERE `parent` IN ({parent_clause}){item_clause}{group}",
        params,
        as_dict=True,
    )
    if group_by_parent:
        return rows
    row = rows[0] if rows else {}
    return {"total": cint(row.get("total")), "grand_total": flt(row.get("grand_total"))}


def _page_treatment_rows(consultation_names: list[str], report_filters: dict, start: int, page_length: int):
    return frappe.get_all(
        "Planned Treatment Item",
        filters=_treatment_filters(consultation_names, report_filters),
        fields=TREATMENT_FIELDS,
        order_by="parent asc, idx asc",
        limit_start=start,
        limit_page_length=page_length,
    )


def _row_totals(page_rows, consultation_map: dict, scoped_consultations: list[dict], item: str | None):
    page_parent_names = sorted({row.get("parent") for row in page_rows if row.get("parent")})
    page_patient_ids = {
        consultation_map.get(parent, {}).get("patient")
        for parent in page_parent_names
        if consultation_map.get(parent, {}).get("patient")
    }
    patient_parent_names = [
        row.get("name")
        for row in scoped_consultations
        if row.get("name") and row.get("patient") in page_patient_ids
    ]
    aggregate_parents = sorted(set(page_parent_names) | set(patient_parent_names))
    aggregates = _aggregate_treatments(aggregate_parents, item=item, group_by_parent=True)
    consultation_totals = {row.get("parent"): flt(row.get("grand_total")) for row in aggregates}
    patient_totals = defaultdict(float)
    for parent in patient_parent_names:
        patient_id = consultation_map.get(parent, {}).get("patient")
        if patient_id:
            patient_totals[patient_id] += flt(consultation_totals.get(parent))
    return consultation_totals, patient_totals


def _render_page_rows(page_rows, scoped_consultations: list[dict], report_filters: dict) -> list[dict]:
    consultation_map = {row.get("name"): row for row in scoped_consultations if row.get("name")}
    patient_ids = {row.get("patient") for row in scoped_consultations if row.get("patient")}
    patient_titles = _get_patient_title_map(patient_ids)
    patient_owners = _patient_owner_map(patient_ids)
    practitioner_names = _get_user_full_name_map(
        row.get("practitioner_user") for row in scoped_consultations if row.get("practitioner_user")
    )
    consultation_totals, patient_totals = _row_totals(
        page_rows,
        consultation_map,
        scoped_consultations,
        cstr(report_filters.get("item") or "").strip() or None,
    )

    output = []
    for treatment in page_rows:
        consultation = consultation_map.get(treatment.get("parent")) or {}
        patient_id = consultation.get("patient")
        qty = flt(treatment.get("qty"))
        rate = flt(treatment.get("rate"))
        amount = flt(treatment.get("amount")) or flt(qty * rate)
        output.append(
            {
                "consultation": treatment.get("parent"),
                "consultation_date": consultation.get("consultation_date"),
                "service_branch": consultation.get("service_branch"),
                "patient": patient_titles.get(patient_id) or patient_id,
                "owner": patient_owners.get(patient_id) or consultation.get("owner"),
                "practitioner": practitioner_names.get(consultation.get("practitioner_user")) or consultation.get("practitioner"),
                "consultation_type": _display_consultation_type(consultation.get("consultation_type")),
                "item": treatment.get("item"),
                "description": treatment.get("notes") or treatment.get("treatment_type") or treatment.get("service_type"),
                "qty": qty,
                "uom": treatment.get("uom"),
                "rate": rate,
                "amount": amount,
                "consultation_total": flt(consultation_totals.get(treatment.get("parent"))),
                "patient_total": flt(patient_totals.get(patient_id)),
                "status": consultation.get("status"),
            }
        )
    return output


@frappe.whitelist()
@frappe.read_only()
def get_planned_treatment_view(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
) -> dict:
    require_internal_user()
    report_filters = _filters(filters)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)

    # Keep the existing consultation resolver as the source of truth for date,
    # branch, practitioner, owner, patient and clinical status scope. It also
    # enforces VetEdge's branch-access check before child treatment rows are read.
    scoped_consultations = _get_consultation_rows(frappe._dict(report_filters))
    consultation_names = [row.get("name") for row in scoped_consultations if row.get("name")]
    if not consultation_names or not frappe.db.exists("DocType", "Planned Treatment Item"):
        return {
            "title": _("Planned Treatment"),
            "subtitle": _("Treatment plans are clinical reports derived from consultations; they are not standalone clinical service records."),
            "columns": _columns(),
            "rows": [],
            "summary": [{"label": _("Grand Total"), "value": 0.0, "indicator": "Green", "datatype": "Currency"}],
            "message": "",
            "start": start,
            "page_length": page_length,
            "total": 0,
            "metadata": {"pagination_mode": "query-level-detail", "parent_scope_mode": "scoped-consultations"},
        }

    aggregate = _aggregate_treatments(
        consultation_names,
        item=cstr(report_filters.get("item") or "").strip() or None,
        group_by_parent=False,
    )
    page_rows = _page_treatment_rows(consultation_names, report_filters, start, page_length)
    rows = _render_page_rows(page_rows, scoped_consultations, report_filters)

    return {
        "title": _("Planned Treatment"),
        "subtitle": _("Treatment plans are clinical reports derived from consultations; they are not standalone clinical service records."),
        "columns": _columns(),
        "rows": rows,
        "summary": [
            {
                "label": _("Grand Total"),
                "value": flt(aggregate.get("grand_total")),
                "indicator": "Green",
                "datatype": "Currency",
            }
        ],
        "message": "",
        "start": start,
        "page_length": page_length,
        "total": cint(aggregate.get("total")),
        "metadata": {
            "pagination_mode": "query-level-detail",
            "parent_scope_mode": "scoped-consultations",
            "detail_rows_materialized": False,
        },
    }
