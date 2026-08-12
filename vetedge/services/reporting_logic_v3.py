from __future__ import annotations

import frappe
from frappe.utils import cstr, flt

from vetedge.services.owner_register_optimized import execute_owner_register
from vetedge.services.reporting_logic_v2 import execute_structured_report as _base_execute_structured_report
from vetedge.services.report_insights import build_report_summary
from vetedge.services.report_visibility import normalize_report_filters


def _execute_base_report(report_name: str, filters=None):
    if report_name == "Owner Register":
        return execute_owner_register(filters)
    return _base_execute_structured_report(report_name, filters)


def execute_structured_report(report_name: str, filters=None):
    filters = normalize_report_filters(report_name, filters)
    columns, data, message, chart, summary = _execute_base_report(report_name, filters)
    filters = frappe._dict(filters or {})
    branch = cstr(filters.get("branch") or "").strip()
    
    # Resolve comparison period data if report supports comparisons
    prev_data = []
    from vetedge.services.report_metadata import get_report_definition
    definition = get_report_definition(report_name)
    if definition and definition.get("capabilities", {}).get("supports_comparison") and filters:
        from_date = filters.get("from_date")
        to_date = filters.get("to_date")
        if from_date and to_date:
            from datetime import timedelta
            from frappe.utils import getdate
            try:
                d_from = getdate(from_date)
                d_to = getdate(to_date)
                duration = (d_to - d_from).days + 1
                prev_to = d_from - timedelta(days=1)
                prev_from = prev_to - timedelta(days=duration - 1)
                
                prev_filters = filters.copy()
                prev_filters["from_date"] = prev_from.strftime("%Y-%m-%d")
                prev_filters["to_date"] = prev_to.strftime("%Y-%m-%d")
                
                _, p_data, _, _, _ = _execute_base_report(report_name, prev_filters)
                prev_data = p_data
            except Exception:
                pass

    if not branch:
        return columns, data, message, chart, build_report_summary(report_name, data, filters, summary, prev_rows=prev_data)

    if report_name in {"Consultation Register", "Planned Treatment", "Lab Order Report", "Vaccination Report", "Boarding Report", "Grooming Report"}:
        data = [row for row in data if cstr(row.get("service_branch")) == branch]
        prev_data = [row for row in prev_data if cstr(row.get("service_branch")) == branch]
    elif report_name == "Patient Register":
        data = [row for row in data if cstr(row.get("default_branch")) == branch]
        prev_data = [row for row in prev_data if cstr(row.get("default_branch")) == branch]
    elif report_name in {"Revenue Summary", "Unpaid Invoice Report"}:
        normalized = []
        for row in data:
            row_branch = cstr(row.get("branch") or "").strip()
            if not row_branch:
                row_branch = _derive_invoice_branch(row.get("invoice"))
                if row_branch:
                    row["branch"] = row_branch
            if row_branch == branch:
                normalized.append(row)
        data = normalized

        prev_normalized = []
        for row in prev_data:
            row_branch = cstr(row.get("branch") or "").strip()
            if not row_branch:
                row_branch = _derive_invoice_branch(row.get("invoice"))
                if row_branch:
                    row["branch"] = row_branch
            if row_branch == branch:
                prev_normalized.append(row)
        prev_data = prev_normalized
    elif report_name in {"Dispensary Activity Report", "Stock Usage Summary", "Branch Performance Report"}:
        data = [row for row in data if cstr(row.get("branch")) == branch]
        prev_data = [row for row in prev_data if cstr(row.get("branch")) == branch]

    if report_name == "Revenue Summary":
        summary = [
            {"label": "Revenue", "value": sum(flt(row.get("grand_total")) for row in data), "indicator": "Green"},
            {"label": "Paid", "value": sum(flt(row.get("paid_amount")) for row in data), "indicator": "Blue"},
            {"label": "Outstanding", "value": sum(flt(row.get("outstanding_amount")) for row in data), "indicator": "Orange"},
        ]

    summary = build_report_summary(report_name, data, filters, summary, prev_rows=prev_data)

    return columns, data, message, chart, summary


def _derive_invoice_branch(invoice_name):
    if not invoice_name:
        return ""
    linked_doctypes = [
        ("Veterinary Consultation", ["linked_invoice", "invoice", "sales_invoice"], ["service_branch", "branch"]),
        ("Veterinary Vaccination Record", ["linked_invoice"], ["service_branch", "branch"]),
        ("Pet Boarding Booking", ["linked_invoice"], ["service_branch", "branch"]),
        ("Pet Grooming Session", ["linked_invoice"], ["service_branch", "branch"]),
        ("Veterinary Lab Order", ["linked_invoice", "invoice"], ["service_branch", "branch"]),
    ]
    for doctype, invoice_fields, branch_fields in linked_doctypes:
        if not frappe.db.exists("DocType", doctype):
            continue
        meta = frappe.get_meta(doctype)
        invoice_field = next((field for field in invoice_fields if meta.get_field(field)), None)
        branch_field = next((field for field in branch_fields if meta.get_field(field)), None)
        if not invoice_field or not branch_field:
            continue
        rows = frappe.get_all(doctype, filters={invoice_field: invoice_name}, fields=[branch_field], limit=1)
        if rows and rows[0].get(branch_field):
            return cstr(rows[0].get(branch_field))
    return ""
