from __future__ import annotations

import frappe
from frappe.utils import cstr, flt

from vetedge.services.reporting_logic_v2 import execute_structured_report as _base_execute_structured_report
from vetedge.services.report_visibility import normalize_report_filters


def execute_structured_report(report_name: str, filters=None):
    filters = normalize_report_filters(report_name, filters)
    columns, data, message, chart, summary = _base_execute_structured_report(report_name, filters)
    filters = frappe._dict(filters or {})
    branch = cstr(filters.get("branch") or "").strip()
    if not branch:
        return columns, data, message, chart, summary

    if report_name in {"Consultation Register", "Lab Order Report", "Vaccination Report", "Boarding Report", "Grooming Report"}:
        data = [row for row in data if cstr(row.get("service_branch")) == branch]
    elif report_name == "Patient Register":
        data = [row for row in data if cstr(row.get("default_branch")) == branch]
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
    elif report_name in {"Dispensary Activity Report", "Stock Usage Summary", "Branch Performance Report"}:
        data = [row for row in data if cstr(row.get("branch")) == branch]

    if report_name == "Revenue Summary":
        summary = [
            {"label": "Revenue", "value": sum(flt(row.get("grand_total")) for row in data), "indicator": "Green"},
            {"label": "Paid", "value": sum(flt(row.get("paid_amount")) for row in data), "indicator": "Blue"},
            {"label": "Outstanding", "value": sum(flt(row.get("outstanding_amount")) for row in data), "indicator": "Orange"},
        ]

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
