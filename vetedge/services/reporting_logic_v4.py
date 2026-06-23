from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import add_days, cstr, flt, getdate, nowdate

from vetedge.services.reporting_logic_v3 import execute_structured_report
from vetedge.services.report_visibility import normalize_dashboard_filters, validate_dashboard_access


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
    filters = _to_dict(filters)
    key = cstr(dashboard_key or "").strip()
    validate_dashboard_access(key)
    filters = normalize_dashboard_filters(key, filters)
    today = cstr(nowdate())
    month_start = cstr(getdate(nowdate()).replace(day=1))

    month_filters = frappe._dict(filters.copy())
    month_filters.from_date = cstr(filters.get("from_date") or month_start)
    month_filters.to_date = cstr(filters.get("to_date") or today)

    today_filters = frappe._dict(filters.copy())
    today_filters.from_date = today
    today_filters.to_date = today

    titles = {
        "executive": _("VetEdge Executive Dashboard"),
        "clinical": _("Clinical Dashboard"),
        "financial": _("Financial Dashboard"),
        "practitioner_performance": _("Practitioner Performance Dashboard"),
        "branch_performance": _("Branch Performance Dashboard"),
        "inventory_dispensary": _("Inventory / Dispensary Dashboard"),
        "lab": _("Lab Dashboard"),
        "vaccination": _("Vaccination Dashboard"),
        "boarding": _("Boarding Dashboard"),
        "grooming": _("Grooming Dashboard"),
    }

    payload = {
        "title": titles.get(key, _("VetEdge Dashboard")),
        "dashboard_key": key,
        "generated_on": today,
        "kpis": [],
        "charts": [],
        "report_links": _dashboard_report_links(key),
        "notes": [],
    }

    if key == "executive":
        consultation_rows = _rows("Consultation Register", today_filters)
        revenue_rows = _rows("Revenue Summary", today_filters)
        unpaid_rows = _rows("Unpaid Invoice Report", filters)
        payload["kpis"] = [
            _kpi(_("Today's Consultations"), len(consultation_rows)),
            _kpi(_("Today's Revenue"), _currency(sum(flt(row.get("grand_total")) for row in revenue_rows))),
            _kpi(_("Unpaid Invoices"), len(unpaid_rows)),
            _kpi(_("Appointments Today"), _appointments_today(filters)),
            _kpi(_("Active Patients"), _active_patients(filters)),
        ]
        payload["charts"] = []
        if _is_multi_day_range(month_filters):
            payload["charts"].append(_consultation_chart(_rows("Consultation Register", month_filters)))
        payload["charts"].extend([
            _consultation_by_branch_chart(_rows("Consultation Register", month_filters)),
            _consultation_type_chart(_rows("Consultation Register", month_filters)),
            _daily_revenue_chart(_rows("Revenue Summary", month_filters)),
            _branch_revenue_chart(_rows("Revenue Summary", month_filters)),
        ])
        return payload

    if key == "financial":
        revenue_rows = _rows("Revenue Summary", month_filters)
        unpaid_rows = _rows("Unpaid Invoice Report", filters)
        payload["kpis"] = [
            _kpi(_("Revenue This Month"), _currency(sum(flt(row.get("grand_total")) for row in revenue_rows))),
            _kpi(_("Outstanding Amount"), _currency(sum(flt(row.get("outstanding_amount")) for row in revenue_rows))),
            _kpi(_("Paid Amount This Month"), _currency(sum(flt(row.get("paid_amount")) for row in revenue_rows))),
        ]
        payload["charts"] = [
            _daily_revenue_chart(revenue_rows),
            _branch_revenue_chart(revenue_rows),
            _unpaid_status_chart(unpaid_rows),
        ]
        return payload

    if key == "inventory_dispensary":
        activity_rows = _rows("Dispensary Activity Report", month_filters)
        usage_rows = _rows("Stock Usage Summary", month_filters)
        payload["kpis"] = [
            _kpi(_("Dispense Events"), len(activity_rows)),
            _kpi(_("Items Issued"), round(sum(flt(row.get("qty")) for row in activity_rows), 2)),
            _kpi(_("Tracked Items"), len(usage_rows)),
        ]
        payload["charts"] = [_stock_usage_chart(usage_rows)]
        return payload

    if key == "grooming":
        grooming_rows = _rows("Grooming Report", month_filters)
        payload["kpis"] = [
            _kpi(_("Grooming Sessions Today"), len(_rows("Grooming Report", today_filters))),
            _kpi(_("Grooming Revenue This Month"), _currency(sum(flt(row.get("total_charge")) for row in grooming_rows))),
        ]
        payload["charts"] = [_grooming_chart(grooming_rows)]
        return payload

    if key == "branch_performance":
        branch_rows = [row for row in _rows("Branch Performance Report", month_filters) if cstr(row.get("branch")) and cstr(row.get("branch")) != "Unassigned"]
        payload["kpis"] = [
            _kpi(_("Branches in Range"), len(branch_rows)),
            _kpi(_("Consultations"), sum(int(row.get("consultation_count") or 0) for row in branch_rows)),
            _kpi(_("Revenue"), _currency(sum(flt(row.get("revenue_total")) for row in branch_rows))),
        ]
        payload["charts"] = [_branch_performance_chart(branch_rows, month_filters)]
        return payload

    if key == "clinical":
        consultation_rows = _rows("Consultation Register", month_filters)
        lab_rows = _rows("Lab Order Report", month_filters)
        vaccination_rows = _rows("Vaccination Report", month_filters)
        due_soon = sum(1 for row in vaccination_rows if cstr(row.get("due_status")) == "Due Soon")
        overdue = sum(1 for row in vaccination_rows if cstr(row.get("due_status")) == "Overdue")
        payload["kpis"] = [
            _kpi(_("Consultations This Month"), len(consultation_rows)),
            _kpi(_("Lab Orders Pending"), sum(1 for row in lab_rows if cstr(row.get("status")) in {"Pending", "Open", "Requested"})),
            _kpi(_("Vaccinations Due Soon"), due_soon),
            _kpi(_("Vaccinations Overdue"), overdue),
        ]
        payload["charts"] = []
        if _is_multi_day_range(month_filters):
            payload["charts"].append(_consultation_chart(consultation_rows))
        payload["charts"].extend([
            _lab_status_chart(lab_rows),
            _vaccination_due_chart(vaccination_rows),
        ])
        return payload

    if key == "lab":
        lab_rows = _rows("Lab Order Report", month_filters)
        payload["kpis"] = [
            _kpi(_("Lab Orders This Month"), len(lab_rows)),
            _kpi(_("Pending"), sum(1 for row in lab_rows if cstr(row.get("status")) in {"Pending", "Open", "Requested"})),
            _kpi(_("Completed"), sum(1 for row in lab_rows if cstr(row.get("status")) == "Completed")),
        ]
        payload["charts"] = [_lab_status_chart(lab_rows)]
        return payload

    if key == "vaccination":
        vaccination_rows = _rows("Vaccination Report", month_filters)
        payload["kpis"] = [
            _kpi(_("Vaccinations This Month"), len(vaccination_rows)),
            _kpi(_("Due Soon"), sum(1 for row in vaccination_rows if cstr(row.get("due_status")) == "Due Soon")),
            _kpi(_("Overdue"), sum(1 for row in vaccination_rows if cstr(row.get("due_status")) == "Overdue")),
        ]
        payload["charts"] = [_vaccination_due_chart(vaccination_rows)]
        return payload

    if key == "boarding":
        boarding_rows = _rows("Boarding Report", month_filters)
        active_rows = [row for row in boarding_rows if cstr(row.get("status")) == "Checked In"]
        payload["kpis"] = [
            _kpi(_("Active Boarding Stays"), len(active_rows)),
            _kpi(_("Boarding Occupancy"), _boarding_occupancy(filters)),
            _kpi(_("Expected Check-outs Today"), sum(1 for row in boarding_rows if cstr(row.get("expected_check_out_date")) == today)),
        ]
        payload["charts"] = [_boarding_chart(_rows("Kennel Availability Report", filters or {"from_date": today, "to_date": add_days(today, 7)}))]
        return payload


    if key == "practitioner_performance":
        practitioner_rows = _rows("Practitioner Performance Report", month_filters)
        payload["kpis"] = [
            _kpi(_("Practitioners in Range"), len({cstr(row.get("practitioner")) for row in practitioner_rows if cstr(row.get("practitioner"))})),
            _kpi(_("Consultations"), sum(int(row.get("number_of_consultations") or 0) for row in practitioner_rows)),
            _kpi(_("Vaccinations"), sum(int(row.get("vaccinations_administered") or 0) for row in practitioner_rows)),
        ]
        payload["charts"] = [_practitioner_revenue_chart(practitioner_rows, month_filters)]
        return payload

    return payload


def _rows(report_name, filters):
    return execute_structured_report(report_name, filters)[1]


def _dashboard_report_links(key):
    links = {
        "executive": ["Consultation Register", "Revenue Summary", "Branch Performance Report"],
        "clinical": ["Consultation Register", "Planned Treatment", "Lab Order Report", "Vaccination Report"],
        "financial": ["Revenue Summary", "Unpaid Invoice Report"],
        "practitioner_performance": ["Practitioner Performance Report"],
        "branch_performance": ["Branch Performance Report"],
        "inventory_dispensary": ["Dispensary Activity Report", "Stock Usage Summary"],
        "lab": ["Lab Order Report"],
        "vaccination": ["Vaccination Report"],
        "boarding": ["Boarding Report", "Kennel Availability Report"],
        "grooming": ["Grooming Report"],
    }
    return [{"label": label, "report": label} for label in links.get(key, [])]


def _group_sum(rows, key_field, value_field):
    grouped = {}
    for row in rows:
        key = cstr(row.get(key_field) or "")
        if not key:
            continue
        grouped[key] = grouped.get(key, 0) + flt(row.get(value_field))
    return grouped


def _group_count(rows, key_field):
    grouped = {}
    for row in rows:
        key = cstr(row.get(key_field) or "")
        if not key:
            continue
        grouped[key] = grouped.get(key, 0) + 1
    return grouped


def _chart(title, chart_type, labels, values, color):
    return {
        "title": title,
        "type": chart_type,
        "data": {"labels": labels, "datasets": [{"name": title, "values": values}]},
        "colors": [color],
        "barOptions": {"stacked": 0},
    }


def _consultation_chart(rows):
    grouped = {}
    for row in rows:
        consultation_date = row.get("consultation_date")
        if not consultation_date:
            continue
        date_key = cstr(getdate(consultation_date))
        grouped[date_key] = grouped.get(date_key, 0) + 1
    labels = sorted(grouped)
    return _chart(_("Consultations per Day"), "line", labels, [grouped[label] for label in labels], "#5b8def")


def _daily_revenue_chart(rows):
    grouped = _group_sum(rows, "posting_date", "grand_total")
    labels = sorted(grouped)
    return _chart(_("Daily Revenue"), "bar", labels, [grouped[label] for label in labels], "#30a46c")


def _branch_revenue_chart(rows):
    grouped = _group_sum(rows, "branch", "grand_total")
    labels = sorted(grouped)
    return _chart(_("Revenue by Branch"), "bar", labels, [grouped[label] for label in labels], "#10b981")


def _consultation_by_branch_chart(rows):
    grouped = _group_count(rows, "service_branch")
    labels = sorted(grouped)
    return _chart(_("Consultations by Branch"), "bar", labels, [grouped[label] for label in labels], "#0ea5e9")


def _consultation_type_chart(rows):
    grouped = {}
    for row in rows:
        consultation_type = cstr(row.get("consultation_type") or _("Unspecified")).strip() or _("Unspecified")
        grouped[consultation_type] = grouped.get(consultation_type, 0) + 1
    labels = sorted(grouped)
    return _chart(_("Consultations by Type"), "donut", labels, [grouped[label] for label in labels], "#6366f1")


def _unpaid_status_chart(rows):
    values = [len(rows)]
    return _chart(_("Unpaid Invoices"), "bar", [_("Outstanding")], values, "#f59e0b")


def _stock_usage_chart(rows):
    labels = [cstr(row.get("item")) for row in rows if row.get("item")]
    values = [flt(row.get("total_qty_issued")) for row in rows if row.get("item")]
    return _chart(_("Stock Usage Summary"), "bar", labels, values, "#8b5cf6")


def _grooming_chart(rows):
    grouped = _group_count(rows, "service_date")
    labels = sorted(grouped)
    return _chart(_("Grooming Sessions"), "line", labels, [grouped[label] for label in labels], "#ec4899")


def _branch_performance_chart(rows, filters=None):
    labels = [cstr(row.get("branch")) for row in rows if row.get("branch")]
    values = [flt(row.get("revenue_total")) for row in rows if row.get("branch")]
    if not labels:
        revenue_rows = _rows("Revenue Summary", filters or {})
        grouped = {}
        for row in revenue_rows:
            branch = cstr(row.get("branch") or "").strip()
            if not branch or branch == "Unassigned":
                continue
            grouped[branch] = grouped.get(branch, 0) + flt(row.get("grand_total"))
        labels = sorted(grouped)
        values = [grouped[label] for label in labels]
    return _chart(_("Revenue by Branch"), "bar", labels, values, "#10b981")


def _lab_status_chart(rows):
    grouped = _group_count(rows, "status")
    labels = sorted(grouped)
    return _chart(_("Lab Orders by Status"), "donut", labels, [grouped[label] for label in labels], "#8b5cf6")


def _vaccination_due_chart(rows):
    due_soon = sum(1 for row in rows if cstr(row.get("due_status")) == "Due Soon")
    overdue = sum(1 for row in rows if cstr(row.get("due_status")) == "Overdue")
    return _chart(_("Vaccinations Due"), "bar", [_("Due Soon"), _("Overdue")], [due_soon, overdue], "#f59e0b")


def _boarding_chart(rows):
    labels = [cstr(row.get("kennel")) for row in rows if row.get("kennel")]
    values = [flt(row.get("current_occupancy")) for row in rows if row.get("kennel")]
    return _chart(_("Boarding Occupancy"), "bar", labels, values, "#0ea5e9")


def _practitioner_revenue_chart(rows, filters=None):
    if rows and any(flt(row.get("revenue_linked_to_consultations")) > 0 for row in rows if row.get("practitioner")):
        return _stacked_practitioner_revenue_chart(rows)

    consultation_rows = _rows("Consultation Register", filters or {})
    revenue_rows = _rows("Revenue Summary", filters or {})
    invoice_totals = {cstr(row.get("invoice")): flt(row.get("grand_total")) for row in revenue_rows if row.get("invoice")}
    grouped = {}
    for row in consultation_rows:
        practitioner = cstr(row.get("practitioner") or "").strip()
        if not practitioner:
            continue
        branch = cstr(row.get("service_branch") or "").strip()
        invoice_name = cstr(row.get("linked_invoice") or "").strip()
        if not invoice_name or invoice_name not in invoice_totals:
            continue
        key = (practitioner, branch or _("Unassigned"))
        grouped[key] = grouped.get(key, 0) + invoice_totals[invoice_name]
    fallback_rows = [
        {
            "practitioner": practitioner,
            "branch": branch,
            "revenue_linked_to_consultations": amount,
        }
        for (practitioner, branch), amount in grouped.items()
    ]
    return _stacked_practitioner_revenue_chart(fallback_rows)


def _stacked_practitioner_revenue_chart(rows):
    grouped = {}
    for row in rows:
        practitioner = cstr(row.get("practitioner") or "").strip()
        if not practitioner:
            continue
        branch = cstr(row.get("branch") or _("Unassigned")).strip() or _("Unassigned")
        grouped.setdefault(practitioner, {})
        grouped[practitioner][branch] = grouped[practitioner].get(branch, 0) + flt(row.get("revenue_linked_to_consultations"))

    labels = sorted(grouped)
    branches = sorted({branch for branch_map in grouped.values() for branch in branch_map})
    palette = ["#6366f1", "#10b981", "#f59e0b", "#0ea5e9", "#ec4899", "#8b5cf6", "#f97316", "#14b8a6"]
    datasets = []
    for index, branch in enumerate(branches):
        datasets.append(
            {
                "name": branch,
                "values": [grouped[practitioner].get(branch, 0) for practitioner in labels],
            }
        )
    return {
        "title": _("Revenue by Practitioner"),
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "colors": [palette[index % len(palette)] for index in range(len(datasets))],
        "barOptions": {"stacked": 1},
    }


def _appointments_today(filters):
    if not frappe.db.exists("DocType", "Veterinary Appointment"):
        return 0
    meta = frappe.get_meta("Veterinary Appointment")
    date_field = "appointment_datetime" if meta.get_field("appointment_datetime") else ("appointment_date" if meta.get_field("appointment_date") else None)
    branch_field = "service_branch" if meta.get_field("service_branch") else ("branch" if meta.get_field("branch") else None)
    if not date_field:
        return 0
    query_filters = {date_field: ("between", [f"{nowdate()} 00:00:00", f"{nowdate()} 23:59:59"])}
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    return frappe.db.count("Veterinary Appointment", query_filters)


def _active_patients(filters):
    if not frappe.db.exists("DocType", "Veterinary Patient"):
        return 0
    meta = frappe.get_meta("Veterinary Patient")
    branch_field = "default_branch" if meta.get_field("default_branch") else ("branch" if meta.get_field("branch") else None)
    status_field = "status" if meta.get_field("status") else None
    query_filters = {}
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if status_field:
        query_filters[status_field] = ("not in", ["Inactive", "Deceased", "Archived"])
    return frappe.db.count("Veterinary Patient", query_filters)


def _boarding_occupancy(filters):
    rows = _rows("Kennel Availability Report", frappe._dict(filters.copy()))
    capacity = sum(flt(row.get("capacity")) for row in rows)
    occupied = sum(flt(row.get("current_occupancy")) for row in rows)
    if not capacity:
        return "0 / 0"
    return f"{int(occupied)} / {int(capacity)} ({round((occupied / capacity) * 100, 1)}%)"


def _kpi(label, value):
    return {"label": label, "value": value}


def _currency(value):
    return frappe.format_value(flt(value), {"fieldtype": "Currency"})


def _to_dict(filters):
    if not filters:
        return frappe._dict()
    if isinstance(filters, str):
        try:
            filters = json.loads(filters)
        except Exception:
            filters = {}
    return frappe._dict(filters)


def _is_multi_day_range(filters) -> bool:
    from_date = cstr(filters.get("from_date") or "").strip()
    to_date = cstr(filters.get("to_date") or "").strip()
    if not from_date or not to_date:
        return True
    try:
        return getdate(to_date) > getdate(from_date)
    except Exception:
        return True
