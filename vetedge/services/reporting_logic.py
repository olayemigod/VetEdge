from __future__ import annotations

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, date_diff, flt, getdate, nowdate


def execute_structured_report(report_name: str, filters=None):
    from vetedge.services.reporting_structure import execute_structured_report as _base_execute

    return _base_execute(report_name, filters)


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
    from vetedge.services.reporting_structure import get_dashboard_payload as _base_dashboard_payload

    return _base_dashboard_payload(dashboard_key, filters)


def resolve_primary_owner_field(doctype, fallback_candidates=None):
    fallback_candidates = fallback_candidates or []
    meta = frappe.get_meta(doctype)
    for fieldname in ["primary_owner", *fallback_candidates]:
        if meta.get_field(fieldname):
            return fieldname
    return None


def invoice_matches_branch(invoice_name, branch):
    if not branch or not invoice_name:
        return True
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
        if rows:
            return cstr(rows[0].get(branch_field)) == cstr(branch)
    return True


def enrich_stock_activity_rows(rows, branch_filter=None):
    consultation_names = sorted({row["consultation"] for row in rows if row.get("consultation")})
    consultation_map = {}
    if consultation_names and frappe.db.exists("DocType", "Veterinary Consultation"):
        meta = frappe.get_meta("Veterinary Consultation")
        patient_field = "patient" if meta.get_field("patient") else None
        branch_field = "service_branch" if meta.get_field("service_branch") else ("branch" if meta.get_field("branch") else None)
        owner_field = "primary_owner" if meta.get_field("primary_owner") else ("owner" if meta.get_field("owner") else None)
        fields = ["name"]
        for fieldname in [patient_field, branch_field, owner_field]:
            if fieldname and fieldname not in fields:
                fields.append(fieldname)
        for row in frappe.get_all("Veterinary Consultation", filters={"name": ("in", consultation_names)}, fields=fields):
            consultation_map[row.name] = {
                "patient": row.get(patient_field),
                "branch": row.get(branch_field),
                "owner": row.get(owner_field),
            }

    enriched = []
    for row in rows:
        context = consultation_map.get(row.get("consultation"), {})
        if not row.get("patient"):
            row["patient"] = context.get("patient")
        if not row.get("branch"):
            row["branch"] = context.get("branch")
        if branch_filter and cstr(row.get("branch")) != cstr(branch_filter):
            continue
        enriched.append(row)
    return enriched


def vaccination_due_state(next_due_date, status):
    if cstr(status) != "Administered" or not next_due_date:
        return "Administered" if cstr(status) == "Administered" else ""
    due_date = getdate(next_due_date)
    today = getdate(nowdate())
    if due_date < today:
        return "Overdue"
    if due_date <= add_days(today, 30):
        return "Due Soon"
    return "Administered"
