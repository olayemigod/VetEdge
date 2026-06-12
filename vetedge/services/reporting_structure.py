from __future__ import annotations

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, date_diff, flt, get_datetime, getdate, nowdate


STANDARD_FIELDS = {
    "name",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "docstatus",
    "idx",
    "parent",
    "parentfield",
    "parenttype",
}

REPORT_KEYS = {
    "Consultation Register": "consultation_register",
    "Patient Register": "patient_register",
    "Owner Register": "owner_register",
    "Practitioner Performance Report": "practitioner_performance_report",
    "Branch Performance Report": "branch_performance_report",
    "Revenue Summary": "revenue_summary",
    "Unpaid Invoice Report": "unpaid_invoice_report",
    "Dispensary Activity Report": "dispensary_activity_report",
    "Stock Usage Summary": "stock_usage_summary",
    "Lab Order Report": "lab_order_report",
    "Vaccination Report": "vaccination_report",
    "Boarding Report": "boarding_report",
    "Kennel Availability Report": "kennel_availability_report",
    "Grooming Report": "grooming_report",
}

DASHBOARD_KEYS = {
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


def _get_user_full_name_map(user_ids):
    user_ids = sorted({cstr(user_id).strip() for user_id in (user_ids or []) if cstr(user_id).strip()})
    if not user_ids or not frappe.db.exists("DocType", "User"):
        return {}
    rows = frappe.get_all("User", filters={"name": ("in", user_ids)}, fields=["name", "full_name"])
    return {row.get("name"): row.get("full_name") or row.get("name") for row in rows}


def _get_patient_title_map(patient_ids):
    patient_ids = sorted({cstr(patient_id).strip() for patient_id in (patient_ids or []) if cstr(patient_id).strip()})
    if not patient_ids or not frappe.db.exists("DocType", "Veterinary Patient"):
        return {}
    title_field = _existing_field("Veterinary Patient", ["patient_name", "title", "animal_name"]) or "name"
    rows = frappe.get_all("Veterinary Patient", filters={"name": ("in", patient_ids)}, fields=["name", title_field])
    return {row.get("name"): row.get(title_field) or row.get("name") for row in rows}


def execute_structured_report(report_name: str, filters=None):
    filters = _to_dict(filters)
    dispatcher = {
        "Consultation Register": _consultation_register,
        "Patient Register": _patient_register,
        "Owner Register": _owner_register,
        "Practitioner Performance Report": _practitioner_performance_report,
        "Branch Performance Report": _branch_performance_report,
        "Revenue Summary": _revenue_summary,
        "Unpaid Invoice Report": _unpaid_invoice_report,
        "Dispensary Activity Report": _dispensary_activity_report,
        "Stock Usage Summary": _stock_usage_summary,
        "Lab Order Report": _lab_order_report,
        "Vaccination Report": _vaccination_report,
        "Boarding Report": _boarding_report,
        "Kennel Availability Report": _kennel_availability_report,
        "Grooming Report": _grooming_report,
    }
    if report_name not in dispatcher:
        return [], [], _("Unknown report: {0}").format(report_name), None, []
    return dispatcher[report_name](filters)


@frappe.whitelist()
def get_dashboard_payload(dashboard_key: str, filters=None):
    filters = _to_dict(filters)
    key = cstr(dashboard_key or "").strip()
    if key not in DASHBOARD_KEYS:
        frappe.throw(_("Unknown dashboard: {0}").format(key))

    today = getdate(nowdate())
    month_start = today.replace(day=1)
    month_filters = frappe._dict(filters.copy())
    month_filters.from_date = cstr(filters.get("from_date") or month_start)
    month_filters.to_date = cstr(filters.get("to_date") or today)

    payload = {
        "title": DASHBOARD_KEYS[key],
        "dashboard_key": key,
        "generated_on": nowdate(),
        "kpis": [],
        "charts": [],
        "report_links": _dashboard_report_links(key),
        "notes": [],
    }

    consultation_rows = _get_consultation_rows(month_filters)
    invoice_rows = _get_sales_invoice_rows(month_filters)
    lab_rows = _get_lab_rows(month_filters)
    vaccination_rows = _get_vaccination_rows(month_filters)
    boarding_rows = _get_boarding_rows(month_filters)
    grooming_rows = _get_grooming_rows(month_filters)
    appointment_rows = _get_appointment_rows(month_filters)

    if key == "executive":
        today_filters = frappe._dict(filters.copy())
        today_filters.from_date = today_filters.to_date = cstr(today)
        payload["kpis"] = [
            _kpi(_("Today's Consultations"), len(_get_consultation_rows(today_filters))),
            _kpi(_("Today's Revenue"), _currency(sum(flt(row.get("grand_total")) for row in _get_sales_invoice_rows(today_filters)))),
            _kpi(_("Unpaid Invoices"), cint(frappe.db.count("Sales Invoice", {"docstatus": 1, "outstanding_amount": (">", 0)}))),
            _kpi(_("Appointments Today"), len(_get_appointment_rows(today_filters))),
            _kpi(_("Active Patients"), _active_patient_count()),
        ]
        payload["charts"] = []
        if _is_multi_day_range(month_filters):
            payload["charts"].append(_consultations_per_day_chart(month_filters))
        payload["charts"].extend([
            _consultations_by_branch_chart(month_filters),
            _daily_revenue_chart(month_filters),
            _revenue_by_branch_chart(month_filters),
        ])
    elif key == "clinical":
        due_soon, overdue = _vaccination_due_counts(vaccination_rows)
        payload["kpis"] = [
            _kpi(_("Consultations This Month"), len(consultation_rows)),
            _kpi(_("Lab Orders Pending"), _count_status(lab_rows, {"Pending", "Open", "Requested"})),
            _kpi(_("Vaccinations Due Soon"), due_soon),
            _kpi(_("Vaccinations Overdue"), overdue),
        ]
        payload["charts"] = []
        if _is_multi_day_range(month_filters):
            payload["charts"].append(_consultations_per_day_chart(month_filters))
        payload["charts"].extend([
            _lab_orders_by_status_chart(month_filters),
            _vaccinations_due_chart(month_filters),
        ])
    elif key == "financial":
        outstanding = sum(flt(row.get("outstanding_amount")) for row in invoice_rows if cint(row.get("docstatus", 0)) != 2)
        revenue = sum(flt(row.get("grand_total")) for row in invoice_rows if cint(row.get("docstatus", 0)) == 1)
        paid = sum(flt(row.get("grand_total")) - flt(row.get("outstanding_amount")) for row in invoice_rows if cint(row.get("docstatus", 0)) == 1)
        payload["kpis"] = [
            _kpi(_("Revenue This Period"), _currency(revenue)),
            _kpi(_("Outstanding Amount"), _currency(outstanding)),
            _kpi(_("Paid Amount This Period"), _currency(paid)),
        ]
        payload["charts"] = [
            _daily_revenue_chart(month_filters),
            _revenue_by_branch_chart(month_filters),
            _revenue_by_practitioner_chart(month_filters),
        ]
    elif key == "boarding":
        active_stays = _active_boarding_stays_count(filters.get("branch"))
        occupancy = _boarding_occupancy_snapshot(filters.get("branch"))
        expected_today = _expected_checkouts_today(filters.get("branch"))
        payload["kpis"] = [
            _kpi(_("Active Boarding Stays"), active_stays),
            _kpi(_("Boarding Occupancy"), occupancy["display"]),
            _kpi(_("Expected Check-outs Today"), expected_today),
        ]
        payload["charts"] = [_boarding_occupancy_chart(month_filters)]
    elif key == "grooming":
        today_filters = frappe._dict(filters.copy())
        today_filters.from_date = today_filters.to_date = cstr(today)
        payload["kpis"] = [
            _kpi(_("Grooming Sessions Today"), len(_get_grooming_rows(today_filters))),
            _kpi(_("Grooming Revenue This Month"), _currency(_sum_grooming_revenue(grooming_rows))),
        ]
        payload["charts"] = [_grooming_sessions_chart(month_filters)]
    elif key == "lab":
        payload["kpis"] = [
            _kpi(_("Lab Orders This Month"), len(lab_rows)),
            _kpi(_("Pending"), _count_status(lab_rows, {"Pending", "Requested", "Open"})),
            _kpi(_("Completed"), _count_status(lab_rows, {"Completed"})),
        ]
        payload["charts"] = [_lab_orders_by_status_chart(month_filters)]
    elif key == "vaccination":
        due_soon, overdue = _vaccination_due_counts(vaccination_rows)
        payload["kpis"] = [
            _kpi(_("Vaccinations This Month"), len(vaccination_rows)),
            _kpi(_("Due Soon"), due_soon),
            _kpi(_("Overdue"), overdue),
        ]
        payload["charts"] = [_vaccinations_due_chart(month_filters)]
    elif key == "branch_performance":
        branch_rows = _build_branch_performance_rows(month_filters)
        payload["kpis"] = [
            _kpi(_("Branches in Range"), len(branch_rows)),
            _kpi(_("Consultations"), sum(cint(row["consultation_count"]) for row in branch_rows)),
            _kpi(_("Revenue"), _currency(sum(flt(row["revenue_total"]) for row in branch_rows))),
        ]
        payload["charts"] = [_revenue_by_branch_chart(month_filters)]
    elif key == "practitioner_performance":
        practitioner_rows = _build_practitioner_performance_rows(month_filters)
        payload["kpis"] = [
            _kpi(_("Practitioners in Range"), len(practitioner_rows)),
            _kpi(_("Consultations"), sum(cint(row["number_of_consultations"]) for row in practitioner_rows)),
            _kpi(_("Vaccinations"), sum(cint(row["vaccinations_administered"]) for row in practitioner_rows)),
        ]
        payload["charts"] = [_revenue_by_practitioner_chart(month_filters)]
    elif key == "inventory_dispensary":
        activity_rows = _build_dispensary_activity_rows(month_filters)
        payload["kpis"] = [
            _kpi(_("Dispense Events"), len(activity_rows)),
            _kpi(_("Items Issued"), flt(sum(flt(row.get("qty")) for row in activity_rows), 2)),
            _kpi(_("Warehouses Touched"), len({row.get("warehouse") for row in activity_rows if row.get("warehouse")})),
        ]

    return payload


def _consultation_register(filters):
    rows = _get_consultation_rows(filters)
    patient_titles = _get_patient_title_map(row.get("patient") for row in rows)
    practitioner_names = _get_user_full_name_map(row.get("practitioner_user") for row in rows)
    columns = [
        _col("consultation", "Link", "Veterinary Consultation"),
        _col("consultation_date", "Date"),
        _col("patient", "Data"),
        _col("owner", "Link", "Customer"),
        _col("practitioner", "Data"),
        _col("service_branch", "Link", "Branch"),
        _col("status", "Data"),
        _col("linked_invoice", "Link", "Sales Invoice"),
    ]
    data = []
    for row in rows:
        data.append(
            {
                "consultation": row.get("name"),
                "consultation_date": row.get("consultation_date"),
                "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
                "owner": row.get("owner"),
                "practitioner": practitioner_names.get(row.get("practitioner_user")) or row.get("practitioner"),
                "service_branch": row.get("service_branch"),
                "status": row.get("status"),
                "linked_invoice": row.get("linked_invoice"),
            }
        )
    return columns, data, None, _chart_for_report("consultation_register", filters, data), []


def _patient_register(filters):
    doctype = "Veterinary Patient"
    patient_name_field = _existing_field(doctype, ["patient_name", "title", "animal_name"]) or "name"
    owner_field = _existing_field(doctype, ["primary_owner", "owner"])
    branch_field = _existing_field(doctype, ["default_branch", "branch", "service_branch"])
    status_field = _existing_field(doctype, ["registration_status", "status"])
    species_field = _existing_field(doctype, ["species"])
    breed_field = _existing_field(doctype, ["breed"])
    query_filters = {}
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if filters.get("owner") and owner_field:
        query_filters[owner_field] = filters.get("owner")
    if filters.get("species") and species_field:
        query_filters[species_field] = filters.get("species")
    if filters.get("registration_status") and status_field:
        query_filters[status_field] = filters.get("registration_status")

    fields = ["name", "creation"]
    for fieldname in [patient_name_field, owner_field, species_field, breed_field, branch_field, status_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    rows = frappe.get_all(doctype, filters=query_filters, fields=fields, order_by="creation desc")
    data = []
    for row in rows:
        data.append(
            {
                "patient": row.get("name"),
                "patient_name": row.get(patient_name_field) if patient_name_field else row.get("name"),
                "primary_owner": row.get(owner_field),
                "species": row.get(species_field),
                "breed": row.get(breed_field),
                "default_branch": row.get(branch_field),
                "registration_status": row.get(status_field),
                "created_on": row.get("creation"),
            }
        )
    columns = [
        _col("patient", "Link", "Veterinary Patient"),
        _col("patient_name", "Data"),
        _col("primary_owner", "Link", "Customer"),
        _col("species", "Data"),
        _col("breed", "Data"),
        _col("default_branch", "Link", "Branch"),
        _col("registration_status", "Data"),
        _col("created_on", "Datetime"),
    ]
    return columns, data, None, None, []


def _owner_register(filters):
    customer_fields = ["name", "customer_name"]
    phone_field = _existing_field("Customer", ["mobile_no", "phone", "phone_number"])
    email_field = _existing_field("Customer", ["email_id", "email"])
    for fieldname in [phone_field, email_field]:
        if fieldname and fieldname not in customer_fields:
            customer_fields.append(fieldname)
    query_filters = {}
    if filters.get("owner"):
        query_filters["name"] = filters.get("owner")

    branch_owner_names = None
    if filters.get("branch") and frappe.db.exists("DocType", "Veterinary Patient"):
        owner_field = _existing_field("Veterinary Patient", ["primary_owner", "owner"])
        branch_field = _existing_field("Veterinary Patient", ["default_branch", "branch", "service_branch"])
        if owner_field and branch_field:
            branch_owner_names = {
                cstr(owner_name).strip()
                for owner_name in frappe.get_all(
                    "Veterinary Patient",
                    filters={branch_field: filters.get("branch")},
                    pluck=owner_field,
                )
                if cstr(owner_name).strip()
            }
            if filters.get("owner"):
                if cstr(filters.get("owner")).strip() not in branch_owner_names:
                    branch_owner_names = set()
            elif branch_owner_names:
                query_filters["name"] = ("in", sorted(branch_owner_names))

    customers = frappe.get_all("Customer", filters=query_filters, fields=customer_fields, order_by="customer_name asc")

    pet_counts = defaultdict(int)
    if frappe.db.exists("DocType", "Veterinary Patient"):
        owner_field = _existing_field("Veterinary Patient", ["primary_owner", "owner"])
        if owner_field:
            for row in frappe.get_all(
                "Veterinary Patient",
                fields=[owner_field, {"COUNT": "name", "as": "pet_count"}],
                group_by=owner_field,
            ):
                pet_counts[row.get(owner_field)] = cint(row.get("pet_count"))

    outstanding = defaultdict(float)
    invoice_filters = {"docstatus": 1, "outstanding_amount": (">", 0)}
    if filters.get("branch") and frappe.get_meta("Sales Invoice").has_field("branch"):
        invoice_filters["branch"] = filters.get("branch")
    for row in frappe.get_all(
        "Sales Invoice",
        filters=invoice_filters,
        fields=["customer", {"SUM": "outstanding_amount", "as": "outstanding_amount"}],
        group_by="customer",
    ):
        outstanding[row.get("customer")] = flt(row.get("outstanding_amount"))

    data = []
    for customer in customers:
        if branch_owner_names is not None and cstr(customer.name).strip() not in branch_owner_names:
            continue
        amount = flt(outstanding.get(customer.name))
        if cint(filters.get("outstanding_only")) and amount <= 0:
            continue
        data.append(
            {
                "owner": customer.name,
                "customer_name": customer.customer_name,
                "phone": customer.get(phone_field),
                "email": customer.get(email_field),
                "number_of_pets": cint(pet_counts.get(customer.name)),
                "outstanding_amount": amount,
            }
        )

    columns = [
        _col("owner", "Link", "Customer"),
        _col("customer_name", "Data"),
        _col("phone", "Data"),
        _col("email", "Data"),
        _col("number_of_pets", "Int"),
        _col("outstanding_amount", "Currency"),
    ]
    return columns, data, None, None, []


def _revenue_summary(filters):
    data = _build_revenue_summary_rows(filters)
    columns = [
        _col("invoice", "Link", "Sales Invoice"),
        _col("posting_date", "Date"),
        _col("customer", "Link", "Customer"),
        _col("branch", "Link", "Branch"),
        _col("cost_center", "Link", "Cost Center"),
        _col("service_category", "Data"),
        _col("grand_total", "Currency"),
        _col("paid_amount", "Currency"),
        _col("outstanding_amount", "Currency"),
        _col("status", "Data"),
    ]
    summary = [
        {"label": _("Revenue"), "value": sum(flt(row["grand_total"]) for row in data), "indicator": "Green"},
        {"label": _("Paid"), "value": sum(flt(row["paid_amount"]) for row in data), "indicator": "Blue"},
        {"label": _("Outstanding"), "value": sum(flt(row["outstanding_amount"]) for row in data), "indicator": "Orange"},
    ]
    return columns, data, None, _chart_for_report("revenue_summary", filters, data), summary


def _unpaid_invoice_report(filters):
    rows = _get_sales_invoice_rows(filters, unpaid_only=True)
    invoice_context = _build_invoice_context_map([row["name"] for row in rows])
    patient_titles = _get_patient_title_map(context.get("patient") for context in invoice_context.values())
    data = []
    for row in rows:
        age_base = getdate(row.get("due_date") or row.get("posting_date") or nowdate())
        age_days = max(0, date_diff(nowdate(), age_base))
        if filters.get("age_range"):
            age_range = cstr(filters.get("age_range"))
            if age_range == "0-30" and not (0 <= age_days <= 30):
                continue
            if age_range == "31-60" and not (31 <= age_days <= 60):
                continue
            if age_range == "61-90" and not (61 <= age_days <= 90):
                continue
            if age_range == "90+" and age_days < 91:
                continue
        context = invoice_context.get(row["name"], {})
        data.append(
            {
                "invoice": row.get("name"),
                "customer": row.get("customer"),
                "posting_date": row.get("posting_date"),
                "due_date": row.get("due_date"),
                "outstanding_amount": flt(row.get("outstanding_amount")),
                "age_days": age_days,
                "branch": row_branch,
                "cost_center": context.get("cost_center") or row.get("cost_center"),
                "linked_patient": patient_titles.get(context.get("patient")) or context.get("patient"),
            }
        )
    columns = [
        _col("invoice", "Link", "Sales Invoice"),
        _col("customer", "Link", "Customer"),
        _col("posting_date", "Date"),
        _col("due_date", "Date"),
        _col("outstanding_amount", "Currency"),
        _col("age_days", "Int"),
        _col("branch", "Link", "Branch"),
        _col("cost_center", "Link", "Cost Center"),
        _col("linked_patient", "Data"),
    ]
    return columns, data, None, None, []


def _practitioner_performance_report(filters):
    rows = _build_practitioner_performance_rows(filters)
    columns = [
        _col("practitioner", "Data"),
        _col("branch", "Link", "Branch"),
        _col("number_of_consultations", "Int"),
        _col("completed_consultations", "Int"),
        _col("revenue_linked_to_consultations", "Currency"),
        _col("lab_orders_requested", "Int"),
        _col("vaccinations_administered", "Int"),
        _col("follow_up_appointments_created", "Int"),
    ]
    return columns, rows, None, _chart_for_report("practitioner_performance_report", filters, rows), []


def _branch_performance_report(filters):
    rows = _build_branch_performance_rows(filters)
    columns = [
        _col("branch", "Link", "Branch"),
        _col("consultation_count", "Int"),
        _col("appointment_count", "Int"),
        _col("revenue_total", "Currency"),
        _col("outstanding_total", "Currency"),
        _col("lab_order_count", "Int"),
        _col("vaccination_count", "Int"),
        _col("dispensary_action_count", "Int"),
        _col("boarding_revenue", "Currency"),
        _col("grooming_revenue", "Currency"),
        _col("active_boarding_stays", "Int"),
        _col("grooming_sessions", "Int"),
    ]
    return columns, rows, None, _chart_for_report("branch_performance_report", filters, rows), []


def _dispensary_activity_report(filters):
    rows = _build_dispensary_activity_rows(filters)
    patient_titles = _get_patient_title_map(row.get("patient") for row in rows)
    user_names = _get_user_full_name_map(row.get("confirmed_by") for row in rows)
    columns = [
        _col("consultation", "Link", "Veterinary Consultation"),
        _col("patient", "Data"),
        _col("branch", "Link", "Branch"),
        _col("item", "Link", "Item"),
        _col("qty", "Float"),
        _col("warehouse", "Link", "Warehouse"),
        _col("batch_no", "Link", "Batch"),
        _col("confirmed_by", "Data"),
        _col("confirmed_on", "Datetime"),
        _col("stock_entry_reference", "Link", "Stock Entry"),
    ]
    data = []
    for row in rows:
        data.append(
            {
                **row,
                "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
                "confirmed_by": user_names.get(row.get("confirmed_by")) or row.get("confirmed_by"),
            }
        )
    return columns, data, None, None, []


def _stock_usage_summary(filters):
    activity_rows = _build_dispensary_activity_rows(filters)
    grouped = {}
    for row in activity_rows:
        key = (row.get("item"), row.get("branch"), row.get("warehouse"))
        bucket = grouped.setdefault(
            key,
            {
                "item": row.get("item"),
                "branch": row.get("branch"),
                "warehouse": row.get("warehouse"),
                "total_qty_issued": 0.0,
                "number_of_dispense_events": 0,
            },
        )
        bucket["total_qty_issued"] += flt(row.get("qty"))
        bucket["number_of_dispense_events"] += 1
    columns = [
        _col("item", "Link", "Item"),
        _col("total_qty_issued", "Float"),
        _col("branch", "Link", "Branch"),
        _col("warehouse", "Link", "Warehouse"),
        _col("number_of_dispense_events", "Int"),
    ]
    return columns, list(grouped.values()), None, None, []


def _lab_order_report(filters):
    rows = _get_lab_rows(filters)
    patient_titles = _get_patient_title_map(row.get("patient") for row in rows)
    user_names = _get_user_full_name_map(row.get("requested_by") for row in rows)
    columns = [
        _col("lab_order", "Link", "Veterinary Lab Order"),
        _col("patient", "Data"),
        _col("owner", "Link", "Customer"),
        _col("consultation", "Link", "Veterinary Consultation"),
        _col("service_branch", "Link", "Branch"),
        _col("requested_by", "Data"),
        _col("status", "Data"),
        _col("requested_on", "Datetime"),
        _col("result_entered_on", "Datetime"),
        _col("reviewed_on", "Datetime"),
    ]
    data = []
    for row in rows:
        data.append(
            {
                **row,
                "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
                "requested_by": user_names.get(row.get("requested_by")) or row.get("requested_by"),
            }
        )
    return columns, data, None, _chart_for_report("lab_order_report", filters, data), []


def _vaccination_report(filters):
    rows = _get_vaccination_rows(filters)
    patient_titles = _get_patient_title_map(row.get("patient") for row in rows)
    user_names = _get_user_full_name_map(row.get("administered_by") for row in rows)
    due_filter = cstr(filters.get("due_status") or "").strip()
    data = []
    for row in rows:
        due_state = _vaccination_due_state(row.get("next_due_date"), row.get("status"))
        if due_filter == "Administered" and cstr(row.get("status")) != "Administered":
            continue
        if due_filter == "Due Soon" and due_state != "Due Soon":
            continue
        if due_filter == "Overdue" and due_state != "Overdue":
            continue
        row["due_status"] = due_state
        data.append(
            {
                **row,
                "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
                "administered_by": user_names.get(row.get("administered_by")) or row.get("administered_by"),
            }
        )
    columns = [
        _col("vaccination_record", "Link", "Veterinary Vaccination Record"),
        _col("patient", "Data"),
        _col("owner", "Link", "Customer"),
        _col("vaccine", "Link", "Veterinary Vaccine"),
        _col("service_branch", "Link", "Branch"),
        _col("administered_by", "Data"),
        _col("administered_on", "Date"),
        _col("next_due_date", "Date"),
        _col("due_status", "Data"),
        _col("status", "Data"),
        _col("linked_invoice", "Link", "Sales Invoice"),
    ]
    return columns, data, None, _chart_for_report("vaccination_report", filters, data), []


def _boarding_report(filters):
    rows = _get_boarding_rows(filters)
    patient_titles = _get_patient_title_map(row.get("patient") for row in rows)
    columns = [
        _col("booking", "Link", "Pet Boarding Booking"),
        _col("patient", "Data"),
        _col("owner", "Link", "Customer"),
        _col("service_branch", "Link", "Branch"),
        _col("kennel", "Link", "Kennel"),
        _col("check_in_date", "Date"),
        _col("expected_check_out_date", "Date"),
        _col("actual_check_out_date", "Date"),
        _col("status", "Data"),
        _col("billable_days", "Int"),
        _col("total_boarding_charge", "Currency"),
        _col("linked_invoice", "Link", "Sales Invoice"),
    ]
    data = [{**row, "patient": patient_titles.get(row.get("patient")) or row.get("patient")} for row in rows]
    return columns, data, None, _chart_for_report("boarding_report", filters, data), []


def _kennel_availability_report(filters):
    from vetedge.services.boarding import get_kennel_availability

    from_date = cstr(filters.get("from_date") or nowdate())
    to_date = cstr(filters.get("to_date") or add_days(from_date, 7))
    rows = get_kennel_availability(
        branch=filters.get("branch"),
        from_date=from_date,
        to_date=to_date,
        kennel=filters.get("kennel"),
    )
    data = []
    for row in rows:
        if filters.get("status") and cstr(row.get("status")) != cstr(filters.get("status")):
            continue
        data.append(
            {
                "kennel": row.get("kennel"),
                "branch": row.get("branch"),
                "capacity": cint(row.get("capacity")),
                "current_occupancy": cint(row.get("current_occupancy") or row.get("occupied_slots")),
                "available_slots": cint(row.get("available_slots")),
                "status": row.get("status"),
                "active_booking": row.get("active_booking") or row.get("active_reference"),
                "expected_check_out_date": row.get("expected_check_out_date") or row.get("next_expected_release_date"),
            }
        )
    columns = [
        _col("kennel", "Link", "Kennel"),
        _col("branch", "Link", "Branch"),
        _col("capacity", "Int"),
        _col("current_occupancy", "Int"),
        _col("available_slots", "Int"),
        _col("status", "Data"),
        _col("active_booking", "Data"),
        _col("expected_check_out_date", "Date"),
    ]
    return columns, data, None, None, []


def _grooming_report(filters):
    rows = _get_grooming_rows(filters)
    patient_titles = _get_patient_title_map(row.get("patient") for row in rows)
    user_names = _get_user_full_name_map(row.get("assigned_staff") for row in rows)
    columns = [
        _col("grooming_record", "Link", "Pet Grooming Session"),
        _col("patient", "Data"),
        _col("owner", "Link", "Customer"),
        _col("service_branch", "Link", "Branch"),
        _col("grooming_service", "Link", "Pet Grooming Service"),
        _col("assigned_staff", "Data"),
        _col("service_date", "Datetime"),
        _col("status", "Data"),
        _col("total_charge", "Currency"),
        _col("linked_invoice", "Link", "Sales Invoice"),
    ]
    data = []
    for row in rows:
        data.append(
            {
                **row,
                "patient": patient_titles.get(row.get("patient")) or row.get("patient"),
                "assigned_staff": user_names.get(row.get("assigned_staff")) or row.get("assigned_staff"),
            }
        )
    return columns, data, None, _chart_for_report("grooming_report", filters, data), []


def _get_consultation_rows(filters):
    doctype = "Veterinary Consultation"
    if not frappe.db.exists("DocType", doctype):
        return []
    date_field = _existing_field(doctype, ["consultation_date", "service_date", "appointment_date", "creation"]) or "creation"
    patient_field = _existing_field(doctype, ["patient"])
    owner_field = _existing_field(doctype, ["primary_owner", "owner"])
    practitioner_filter_field = _existing_field(doctype, ["consulting_practitioner", "practitioner", "doctor", "veterinarian"])
    practitioner_name_field = _existing_field(doctype, ["consulting_practitioner_name", "practitioner_name"])
    branch_field = _existing_field(doctype, ["service_branch", "branch"])
    status_field = _existing_field(doctype, ["status"])
    invoice_field = _existing_field(doctype, ["linked_invoice", "invoice", "sales_invoice"])
    query_filters = _date_filter_dict(date_field, filters, 30)
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if filters.get("practitioner") and practitioner_filter_field:
        query_filters[practitioner_filter_field] = filters.get("practitioner")
    if filters.get("status") and status_field:
        query_filters[status_field] = filters.get("status")
    if filters.get("patient") and patient_field:
        query_filters[patient_field] = filters.get("patient")
    if filters.get("owner") and owner_field:
        query_filters[owner_field] = filters.get("owner")
    fields = ["name"]
    for fieldname in [date_field, patient_field, owner_field, practitioner_filter_field, practitioner_name_field, branch_field, status_field, invoice_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    raw_rows = frappe.get_all(doctype, filters=query_filters, fields=fields, order_by=f"{date_field} desc")
    rows = []
    for row in raw_rows:
        rows.append(
            {
                "name": row.get("name"),
                "consultation_date": row.get(date_field),
                "patient": row.get(patient_field),
                "owner": row.get(owner_field),
                "practitioner": row.get(practitioner_name_field) or row.get(practitioner_filter_field),
                "practitioner_user": row.get(practitioner_filter_field),
                "service_branch": row.get(branch_field),
                "status": row.get(status_field),
                "linked_invoice": row.get(invoice_field),
            }
        )
    return rows


def _get_sales_invoice_rows(filters, unpaid_only=False):
    doctype = "Sales Invoice"
    if not frappe.db.exists("DocType", doctype):
        return []
    branch_field = _existing_field(doctype, ["branch", "service_branch"])
    cost_center_field = _existing_field(doctype, ["cost_center"])
    status_field = _existing_field(doctype, ["status"]) or "status"
    query_filters = _date_filter_dict("posting_date", filters, 30)
    if filters.get("cost_center") and cost_center_field:
        query_filters[cost_center_field] = filters.get("cost_center")
    if filters.get("status") and status_field:
        query_filters[status_field] = filters.get("status")
    if filters.get("customer"):
        query_filters["customer"] = filters.get("customer")
    if unpaid_only:
        query_filters["docstatus"] = 1
        query_filters["outstanding_amount"] = (">", 0)
    else:
        query_filters["docstatus"] = ("<", 2)
    fields = ["name", "posting_date", "customer", "grand_total", "outstanding_amount", "docstatus", "due_date"]
    for fieldname in [branch_field, cost_center_field, status_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    return frappe.get_all(doctype, filters=query_filters, fields=fields, order_by="posting_date desc")


def _build_revenue_summary_rows(filters):
    rows = _get_sales_invoice_rows(filters)
    invoice_context = _build_invoice_context_map([row["name"] for row in rows])
    data = []
    for row in rows:
        context = invoice_context.get(row["name"], {})
        row_branch = context.get("branch") or row.get("branch")
        if filters.get("branch") and cstr(row_branch) != cstr(filters.get("branch")):
            continue
        service_category = context.get("service_category") or _("General")
        if filters.get("service_category") and service_category != filters.get("service_category"):
            continue
        data.append(
            {
                "invoice": row.get("name"),
                "posting_date": row.get("posting_date"),
                "customer": row.get("customer"),
                "branch": row_branch,
                "cost_center": context.get("cost_center") or row.get("cost_center"),
                "service_category": service_category,
                "grand_total": flt(row.get("grand_total")),
                "paid_amount": flt(row.get("grand_total")) - flt(row.get("outstanding_amount")),
                "outstanding_amount": flt(row.get("outstanding_amount")),
                "status": row.get("status") or _invoice_status_from_row(row),
            }
        )
    return data


def _build_practitioner_performance_rows(filters):
    consultations = _get_consultation_rows(filters)
    metrics = {}
    invoice_names_by_bucket = defaultdict(set)
    user_labels = {}
    full_name_to_users = {}

    def _normalize_practitioner_identity(value):
        value = cstr(value or "").strip()
        if not value:
            return ""
        if frappe.db.exists("User", value):
            return value
        if value not in full_name_to_users:
            matches = frappe.get_all("User", filters={"full_name": value}, pluck="name")
            full_name_to_users[value] = matches or []
        matches = full_name_to_users.get(value) or []
        if len(matches) == 1:
            return matches[0]
        return value

    def _display_practitioner(value):
        identity = _normalize_practitioner_identity(value)
        if not identity:
            return _("Unassigned")
        if "@" not in identity:
            return identity
        if identity not in user_labels:
            full_name = frappe.db.get_value("User", identity, "full_name")
            user_labels[identity] = full_name or identity
        return user_labels[identity]

    def _bucket_identity(practitioner_value):
        identity = _normalize_practitioner_identity(practitioner_value)
        if not identity:
            return _("Unassigned")
        if "@" not in identity:
            return identity
        if identity not in user_labels:
            full_name = frappe.db.get_value("User", identity, "full_name")
            user_labels[identity] = full_name or identity
        return identity

    def _bucket_key(practitioner_value, branch_value):
        return (_bucket_identity(practitioner_value), branch_value or _("Unassigned"))

    def _ensure_bucket(practitioner_value, branch_value):
        key = _bucket_key(practitioner_value, branch_value)
        if key not in metrics:
            metrics[key] = {
                "practitioner": _display_practitioner(practitioner_value),
                "branch": key[1],
                "number_of_consultations": 0,
                "completed_consultations": 0,
                "revenue_linked_to_consultations": 0.0,
                "lab_orders_requested": 0,
                "vaccinations_administered": 0,
                "follow_up_appointments_created": 0,
            }
        return key

    for row in consultations:
        key = _ensure_bucket(row.get("practitioner_user") or row.get("practitioner"), row.get("service_branch"))
        bucket = metrics[key]
        bucket["number_of_consultations"] += 1
        if cstr(row.get("status")).lower() == "completed":
            bucket["completed_consultations"] += 1
        if row.get("linked_invoice"):
            invoice_names_by_bucket[key].add(row.get("linked_invoice"))

    invoice_map = {row["name"]: row for row in _get_sales_invoice_rows(filters)}
    for key, invoice_names in invoice_names_by_bucket.items():
        metrics[key]["revenue_linked_to_consultations"] = sum(
            flt(invoice_map.get(name, {}).get("grand_total")) for name in invoice_names
        )

    for row in _get_lab_rows(filters):
        key = _ensure_bucket(row.get("requested_by"), row.get("service_branch"))
        metrics[key]["lab_orders_requested"] += 1

    for row in _get_vaccination_rows(filters):
        key = _ensure_bucket(row.get("administered_by"), row.get("service_branch"))
        metrics[key]["vaccinations_administered"] += 1

    for row in _get_appointment_rows(filters):
        key = _ensure_bucket(row.get("practitioner"), row.get("service_branch"))
        metrics[key]["follow_up_appointments_created"] += 1

    return sorted(metrics.values(), key=lambda row: (cstr(row["practitioner"]), cstr(row["branch"])))


def _build_branch_performance_rows(filters):
    consultation_rows = _get_consultation_rows(filters)
    appointment_rows = _get_appointment_rows(filters)
    revenue_rows = _build_revenue_summary_rows(filters)
    lab_rows = _get_lab_rows(filters)
    vaccination_rows = _get_vaccination_rows(filters)
    dispensary_rows = _build_dispensary_activity_rows(filters)
    active_stays = _get_active_boarding_stays(filters)
    grooming_rows = _get_grooming_rows(filters)

    metrics = defaultdict(
        lambda: {
            "branch": "",
            "consultation_count": 0,
            "appointment_count": 0,
            "revenue_total": 0.0,
            "outstanding_total": 0.0,
            "lab_order_count": 0,
            "vaccination_count": 0,
            "dispensary_action_count": 0,
            "boarding_revenue": 0.0,
            "grooming_revenue": 0.0,
            "active_boarding_stays": 0,
            "grooming_sessions": 0,
        }
    )

    def bucket(branch_name):
        key = branch_name or _("Unassigned")
        metrics[key]["branch"] = key
        return metrics[key]

    for row in consultation_rows:
        bucket(row.get("service_branch"))["consultation_count"] += 1
    for row in appointment_rows:
        bucket(row.get("service_branch"))["appointment_count"] += 1
    for row in revenue_rows:
        branch_bucket = bucket(row.get("branch"))
        branch_bucket["revenue_total"] += flt(row.get("grand_total"))
        branch_bucket["outstanding_total"] += flt(row.get("outstanding_amount"))
        category = cstr(row.get("service_category"))
        if category == "Boarding":
            branch_bucket["boarding_revenue"] += flt(row.get("grand_total"))
        if category == "Grooming":
            branch_bucket["grooming_revenue"] += flt(row.get("grand_total"))
    for row in lab_rows:
        bucket(row.get("service_branch"))["lab_order_count"] += 1
    for row in vaccination_rows:
        bucket(row.get("service_branch"))["vaccination_count"] += 1
    for row in dispensary_rows:
        bucket(row.get("branch"))["dispensary_action_count"] += 1
    for row in active_stays:
        bucket(row.get("service_branch"))["active_boarding_stays"] += 1
    for row in grooming_rows:
        branch_bucket = bucket(row.get("service_branch"))
        branch_bucket["grooming_sessions"] += 1

    rows = list(metrics.values())
    if filters.get("branch"):
        rows = [row for row in rows if row["branch"] == filters.get("branch")]
    return sorted(rows, key=lambda row: cstr(row["branch"]))


def _build_dispensary_activity_rows(filters):
    from vetedge.services.stock import STOCK_ENTRY_CONSULTATION_FIELD

    stock_entry_filters = _date_filter_dict("posting_date", filters, 30)
    stock_entry_filters["docstatus"] = 1
    detail_fields = ["parent", "item_code", "qty", "batch_no", "s_warehouse", "t_warehouse"]
    if filters.get("item"):
        detail_filters = {"item_code": filters.get("item")}
    else:
        detail_filters = {}
    details = frappe.get_all("Stock Entry Detail", filters=detail_filters, fields=detail_fields, order_by="modified desc")
    if not details:
        return []
    parent_names = sorted({row.parent for row in details if row.parent})
    parent_fields = ["name", "posting_date", "owner", "modified", "stock_entry_type", "purpose"]
    branch_field = _existing_field("Stock Entry", ["branch", "service_branch"])
    consultation_field = STOCK_ENTRY_CONSULTATION_FIELD if frappe.get_meta("Stock Entry").has_field(STOCK_ENTRY_CONSULTATION_FIELD) else _existing_field("Stock Entry", ["consultation", "linked_consultation"])
    patient_field = _existing_field("Stock Entry", ["patient", "linked_patient"])
    for fieldname in [branch_field, consultation_field, patient_field]:
        if fieldname and fieldname not in parent_fields:
            parent_fields.append(fieldname)
    parents = {
        row.name: row
        for row in frappe.get_all(
            "Stock Entry",
            filters={"name": ("in", parent_names), **stock_entry_filters},
            fields=parent_fields,
        )
    }
    consultation_names = sorted({parent.get(consultation_field) for parent in parents.values() if consultation_field and parent.get(consultation_field)})
    consultation_context = {}
    if consultation_names and frappe.db.exists("DocType", "Veterinary Consultation"):
        consultation_context = {
            row.name: row
            for row in frappe.get_all(
                "Veterinary Consultation",
                filters={"name": ("in", consultation_names)},
                fields=["name", "patient", "service_branch"],
            )
        }

    rows = []
    for detail in details:
        parent = parents.get(detail.parent)
        if not parent:
            continue
        warehouse = detail.get("s_warehouse") or detail.get("t_warehouse")
        consultation_name = parent.get(consultation_field) if consultation_field else None
        context = consultation_context.get(consultation_name, {})
        branch_value = parent.get(branch_field) or context.get("service_branch")
        patient_value = parent.get(patient_field) or context.get("patient")
        if filters.get("warehouse") and warehouse != filters.get("warehouse"):
            continue
        if filters.get("branch") and cstr(branch_value) != cstr(filters.get("branch")):
            continue
        rows.append(
            {
                "consultation": consultation_name,
                "patient": patient_value,
                "branch": branch_value,
                "item": detail.get("item_code"),
                "qty": flt(detail.get("qty")),
                "warehouse": warehouse,
                "batch_no": detail.get("batch_no"),
                "confirmed_by": parent.get("owner"),
                "confirmed_on": parent.get("modified"),
                "stock_entry_reference": parent.get("name"),
            }
        )
    return rows


def _get_lab_rows(filters):
    doctype = "Veterinary Lab Order"
    if not frappe.db.exists("DocType", doctype):
        return []
    patient_field = _existing_field(doctype, ["patient"])
    owner_field = _existing_field(doctype, ["primary_owner", "owner"])
    consultation_field = _existing_field(doctype, ["consultation", "linked_consultation"])
    branch_field = _existing_field(doctype, ["service_branch", "branch"])
    requested_by_field = _existing_field(doctype, ["requested_by", "doctor", "practitioner"])
    status_field = _existing_field(doctype, ["status"])
    requested_on_field = _existing_field(doctype, ["requested_on", "creation"]) or "creation"
    result_on_field = _existing_field(doctype, ["result_entered_on", "completed_on", "result_date"])
    reviewed_on_field = _existing_field(doctype, ["reviewed_on"])
    query_filters = _date_filter_dict(requested_on_field, filters, 30)
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if filters.get("status") and status_field:
        query_filters[status_field] = filters.get("status")
    if filters.get("requested_by") and requested_by_field:
        query_filters[requested_by_field] = filters.get("requested_by")
    if filters.get("practitioner") and requested_by_field:
        query_filters[requested_by_field] = filters.get("practitioner")
    if filters.get("patient") and patient_field:
        query_filters[patient_field] = filters.get("patient")
    fields = ["name"]
    for fieldname in [patient_field, owner_field, consultation_field, branch_field, requested_by_field, status_field, requested_on_field, result_on_field, reviewed_on_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    raw_rows = frappe.get_all(doctype, filters=query_filters, fields=fields, order_by=f"{requested_on_field} desc")
    return [
        {
            "lab_order": row.get("name"),
            "patient": row.get(patient_field),
            "owner": row.get(owner_field),
            "consultation": row.get(consultation_field),
            "service_branch": row.get(branch_field),
            "requested_by": row.get(requested_by_field),
            "status": row.get(status_field),
            "requested_on": row.get(requested_on_field),
            "result_entered_on": row.get(result_on_field),
            "reviewed_on": row.get(reviewed_on_field),
        }
        for row in raw_rows
    ]


def _get_vaccination_rows(filters):
    doctype = "Veterinary Vaccination Record"
    if not frappe.db.exists("DocType", doctype):
        return []
    patient_field = _existing_field(doctype, ["patient"])
    owner_field = _existing_field(doctype, ["primary_owner", "owner"])
    vaccine_field = _existing_field(doctype, ["vaccine"])
    branch_field = _existing_field(doctype, ["service_branch", "branch"])
    administered_by_field = _existing_field(doctype, ["administered_by"])
    administered_on_field = _existing_field(doctype, ["administered_on", "creation"]) or "creation"
    next_due_date_field = _existing_field(doctype, ["next_due_date"])
    status_field = _existing_field(doctype, ["status"])
    invoice_field = _existing_field(doctype, ["linked_invoice"])
    query_filters = _date_filter_dict(administered_on_field, filters, 30)
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if filters.get("status") and status_field:
        query_filters[status_field] = filters.get("status")
    if filters.get("practitioner") and administered_by_field:
        query_filters[administered_by_field] = filters.get("practitioner")
    if filters.get("patient") and patient_field:
        query_filters[patient_field] = filters.get("patient")
    if filters.get("owner") and owner_field:
        query_filters[owner_field] = filters.get("owner")
    if filters.get("vaccine") and vaccine_field:
        query_filters[vaccine_field] = filters.get("vaccine")
    fields = ["name"]
    for fieldname in [patient_field, owner_field, vaccine_field, branch_field, administered_by_field, administered_on_field, next_due_date_field, status_field, invoice_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    raw_rows = frappe.get_all(doctype, filters=query_filters, fields=fields, order_by=f"{administered_on_field} desc")
    return [
        {
            "vaccination_record": row.get("name"),
            "patient": row.get(patient_field),
            "owner": row.get(owner_field),
            "vaccine": row.get(vaccine_field),
            "service_branch": row.get(branch_field),
            "administered_by": row.get(administered_by_field),
            "administered_on": row.get(administered_on_field),
            "next_due_date": row.get(next_due_date_field),
            "status": row.get(status_field),
            "linked_invoice": row.get(invoice_field),
        }
        for row in raw_rows
    ]


def _get_boarding_rows(filters):
    doctype = "Pet Boarding Booking"
    if not frappe.db.exists("DocType", doctype):
        return []
    patient_field = _existing_field(doctype, ["patient"])
    owner_field = _existing_field(doctype, ["primary_owner", "owner"])
    branch_field = _existing_field(doctype, ["service_branch", "branch"])
    kennel_field = _existing_field(doctype, ["kennel"])
    check_in_field = _existing_field(doctype, ["check_in_date"]) or "creation"
    expected_out_field = _existing_field(doctype, ["expected_check_out_date"])
    actual_out_field = _existing_field(doctype, ["actual_check_out_date"])
    status_field = _existing_field(doctype, ["status"])
    billable_days_field = _existing_field(doctype, ["billable_days"])
    total_charge_field = _existing_field(doctype, ["total_boarding_charge"])
    invoice_field = _existing_field(doctype, ["linked_invoice"])
    query_filters = _date_filter_dict(check_in_field, filters, 30)
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if filters.get("status") and status_field:
        query_filters[status_field] = filters.get("status")
    if filters.get("patient") and patient_field:
        query_filters[patient_field] = filters.get("patient")
    if filters.get("owner") and owner_field:
        query_filters[owner_field] = filters.get("owner")
    if filters.get("kennel") and kennel_field:
        query_filters[kennel_field] = filters.get("kennel")
    fields = ["name"]
    for fieldname in [patient_field, owner_field, branch_field, kennel_field, check_in_field, expected_out_field, actual_out_field, status_field, billable_days_field, total_charge_field, invoice_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    raw_rows = frappe.get_all(doctype, filters=query_filters, fields=fields, order_by=f"{check_in_field} desc")
    return [
        {
            "booking": row.get("name"),
            "patient": row.get(patient_field),
            "owner": row.get(owner_field),
            "service_branch": row.get(branch_field),
            "kennel": row.get(kennel_field),
            "check_in_date": row.get(check_in_field),
            "expected_check_out_date": row.get(expected_out_field),
            "actual_check_out_date": row.get(actual_out_field),
            "status": row.get(status_field),
            "billable_days": cint(row.get(billable_days_field)),
            "total_boarding_charge": flt(row.get(total_charge_field)),
            "linked_invoice": row.get(invoice_field),
        }
        for row in raw_rows
    ]


def _get_active_boarding_stays(filters):
    doctype = "Pet Boarding Stay"
    if not frappe.db.exists("DocType", doctype):
        return []
    branch_field = _existing_field(doctype, ["service_branch", "branch"])
    status_field = _existing_field(doctype, ["status"])
    filters_dict = {}
    if status_field:
        filters_dict[status_field] = "Active"
    if filters.get("branch") and branch_field:
        filters_dict[branch_field] = filters.get("branch")
    fields = ["name"]
    if branch_field:
        fields.append(branch_field)
    return [
        {"name": row.get("name"), "service_branch": row.get(branch_field)}
        for row in frappe.get_all(doctype, filters=filters_dict, fields=fields)
    ]


def _get_grooming_rows(filters):
    doctype = "Pet Grooming Session"
    if not frappe.db.exists("DocType", doctype):
        return []
    patient_field = _existing_field(doctype, ["patient"])
    owner_field = _existing_field(doctype, ["primary_owner", "owner"])
    branch_field = _existing_field(doctype, ["service_branch", "branch"])
    service_field = _existing_field(doctype, ["grooming_service"])
    groomer_field = _existing_field(doctype, ["groomer", "assigned_staff"])
    status_field = _existing_field(doctype, ["status"])
    invoice_field = _existing_field(doctype, ["linked_invoice"])
    service_date_field = _existing_field(doctype, ["start_time", "service_date", "creation"]) or "creation"
    query_filters = _date_filter_dict(service_date_field, filters, 30)
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if filters.get("status") and status_field:
        query_filters[status_field] = filters.get("status")
    if filters.get("patient") and patient_field:
        query_filters[patient_field] = filters.get("patient")
    if filters.get("owner") and owner_field:
        query_filters[owner_field] = filters.get("owner")
    if filters.get("assigned_staff") and groomer_field:
        query_filters[groomer_field] = filters.get("assigned_staff")
    fields = ["name"]
    for fieldname in [patient_field, owner_field, branch_field, service_field, groomer_field, status_field, invoice_field, service_date_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    raw_rows = frappe.get_all(doctype, filters=query_filters, fields=fields, order_by=f"{service_date_field} desc")
    invoice_map = {row["name"]: row for row in _get_sales_invoice_rows(filters)}
    data = []
    for row in raw_rows:
        invoice_name = row.get(invoice_field)
        invoice_total = flt(invoice_map.get(invoice_name, {}).get("grand_total")) if invoice_name else 0
        data.append(
            {
                "grooming_record": row.get("name"),
                "patient": row.get(patient_field),
                "owner": row.get(owner_field),
                "service_branch": row.get(branch_field),
                "grooming_service": row.get(service_field),
                "assigned_staff": row.get(groomer_field),
                "service_date": row.get(service_date_field),
                "status": row.get(status_field),
                "total_charge": invoice_total,
                "linked_invoice": invoice_name,
            }
        )
    return data


def _get_appointment_rows(filters):
    doctype = "Veterinary Appointment"
    if not frappe.db.exists("DocType", doctype):
        return []
    date_field = _existing_field(doctype, ["appointment_datetime", "appointment_date", "scheduled_on", "creation"]) or "creation"
    branch_field = _existing_field(doctype, ["branch", "service_branch"])
    practitioner_field = _existing_field(doctype, ["doctor", "practitioner"])
    query_filters = _date_filter_dict(date_field, filters, 30)
    if filters.get("branch") and branch_field:
        query_filters[branch_field] = filters.get("branch")
    if filters.get("practitioner") and practitioner_field:
        query_filters[practitioner_field] = filters.get("practitioner")
    fields = ["name", date_field]
    for fieldname in [branch_field, practitioner_field]:
        if fieldname and fieldname not in fields:
            fields.append(fieldname)
    return [
        {
            "name": row.get("name"),
            "appointment_datetime": row.get(date_field),
            "service_branch": row.get(branch_field),
            "practitioner": row.get(practitioner_field),
        }
        for row in frappe.get_all(doctype, filters=query_filters, fields=fields, order_by=f"{date_field} desc")
    ]


def _build_invoice_context_map(invoice_names):
    if not invoice_names:
        return {}
    invoice_names = sorted({name for name in invoice_names if name})
    context = defaultdict(dict)

    for row in _get_sales_invoice_item_rows(invoice_names):
        service_category = _infer_service_category(row.get("description"), row.get("item_code"))
        if service_category and not context[row["parent"]].get("service_category"):
            context[row["parent"]]["service_category"] = service_category
        if row.get("cost_center") and not context[row["parent"]].get("cost_center"):
            context[row["parent"]]["cost_center"] = row.get("cost_center")

    mappings = [
        ("Veterinary Consultation", ["linked_invoice", "invoice", "sales_invoice"], ["service_branch", "branch"], ["patient"], "Consultation"),
        ("Veterinary Vaccination Record", ["linked_invoice"], ["service_branch", "branch"], ["patient"], "Vaccination"),
        ("Pet Boarding Booking", ["linked_invoice"], ["service_branch", "branch"], ["patient"], "Boarding"),
        ("Pet Grooming Session", ["linked_invoice"], ["service_branch", "branch"], ["patient"], "Grooming"),
        ("Veterinary Lab Order", ["linked_invoice", "invoice"], ["service_branch", "branch"], ["patient"], "Lab"),
    ]
    for doctype, invoice_fields, branch_fields, patient_fields, service_category in mappings:
        if not frappe.db.exists("DocType", doctype):
            continue
        invoice_field = _existing_field(doctype, invoice_fields)
        if not invoice_field:
            continue
        branch_field = _existing_field(doctype, branch_fields)
        patient_field = _existing_field(doctype, patient_fields)
        fields = [invoice_field]
        if branch_field:
            fields.append(branch_field)
        if patient_field:
            fields.append(patient_field)
        rows = frappe.get_all(doctype, filters={invoice_field: ("in", invoice_names)}, fields=fields)
        for row in rows:
            invoice_name = row.get(invoice_field)
            if not context[invoice_name].get("branch"):
                context[invoice_name]["branch"] = row.get(branch_field)
            if not context[invoice_name].get("patient"):
                context[invoice_name]["patient"] = row.get(patient_field)
            if not context[invoice_name].get("service_category"):
                context[invoice_name]["service_category"] = service_category
    return context


def _get_sales_invoice_item_rows(invoice_names):
    if not invoice_names:
        return []
    fields = ["parent", "item_code", "description"]
    cost_center_field = _existing_field("Sales Invoice Item", ["cost_center"])
    if cost_center_field:
        fields.append(cost_center_field)
    rows = frappe.get_all(
        "Sales Invoice Item",
        filters={"parent": ("in", invoice_names)},
        fields=fields,
    )
    data = []
    for row in rows:
        data.append(
            {
                "parent": row.get("parent"),
                "item_code": row.get("item_code"),
                "description": row.get("description"),
                "cost_center": row.get(cost_center_field),
            }
        )
    return data


def _chart_for_report(report_key, filters, data):
    chart_slug = cstr(filters.get("chart") or "").strip()
    if not chart_slug:
        return None
    builders = {
        "consultations_per_day": lambda: _consultations_per_day_chart(filters),
        "daily_revenue": lambda: _daily_revenue_chart(filters),
        "lab_orders_by_status": lambda: _lab_orders_by_status_chart(filters),
        "vaccinations_due": lambda: _vaccinations_due_chart(filters),
        "boarding_occupancy": lambda: _boarding_occupancy_chart(filters),
        "grooming_sessions": lambda: _grooming_sessions_chart(filters),
        "revenue_by_branch": lambda: _revenue_by_branch_chart(filters),
        "revenue_by_practitioner": lambda: _revenue_by_practitioner_chart(filters),
    }
    builder = builders.get(chart_slug)
    return builder() if builder else None


def _consultations_per_day_chart(filters):
    rows = _get_consultation_rows(filters)
    grouped = defaultdict(int)
    for row in rows:
        date_key = cstr(getdate(row.get("consultation_date")))
        grouped[date_key] += 1
    labels = sorted(grouped)
    return _chart(_("Consultations per Day"), "line", labels, [grouped[label] for label in labels], "#5b8def")


def _daily_revenue_chart(filters):
    rows = _build_revenue_summary_rows(filters)
    grouped = defaultdict(float)
    for row in rows:
        grouped[cstr(getdate(row.get("posting_date")))] += flt(row.get("grand_total"))
    labels = sorted(grouped)
    return _chart(_("Daily Revenue"), "bar", labels, [grouped[label] for label in labels], "#30a46c")


def _lab_orders_by_status_chart(filters):
    rows = _get_lab_rows(filters)
    grouped = defaultdict(int)
    for row in rows:
        grouped[cstr(row.get("status") or _("Unknown"))] += 1
    labels = sorted(grouped)
    return _chart(_("Lab Orders by Status"), "donut", labels, [grouped[label] for label in labels], "#8b5cf6")


def _vaccinations_due_chart(filters):
    rows = _get_vaccination_rows(filters)
    due_soon, overdue = _vaccination_due_counts(rows)
    labels = [_("Due Soon"), _("Overdue")]
    return _chart(_("Vaccinations Due"), "bar", labels, [due_soon, overdue], "#f59e0b")


def _boarding_occupancy_chart(filters):
    rows = _kennel_availability_report(filters)[1]
    labels = [row.get("kennel") for row in rows]
    values = [cint(row.get("current_occupancy")) for row in rows]
    return _chart(_("Boarding Occupancy"), "bar", labels, values, "#0ea5e9")


def _grooming_sessions_chart(filters):
    rows = _get_grooming_rows(filters)
    grouped = defaultdict(int)
    for row in rows:
        grouped[cstr(getdate(row.get("service_date")))] += 1
    labels = sorted(grouped)
    return _chart(_("Grooming Sessions"), "line", labels, [grouped[label] for label in labels], "#ec4899")


def _revenue_by_branch_chart(filters):
    rows = _build_branch_performance_rows(filters)
    labels = [row.get("branch") for row in rows]
    values = [flt(row.get("revenue_total")) for row in rows]
    return _chart(_("Revenue by Branch"), "bar", labels, values, "#10b981")


def _consultations_by_branch_chart(filters):
    rows = _get_consultation_rows(filters)
    grouped = defaultdict(int)
    for row in rows:
        branch = cstr(row.get("service_branch") or _("Unassigned")).strip() or _("Unassigned")
        grouped[branch] += 1
    labels = sorted(grouped)
    return _chart(_("Consultations by Branch"), "bar", labels, [grouped[label] for label in labels], "#0ea5e9")


def _revenue_by_practitioner_chart(filters):
    rows = _build_practitioner_performance_rows(filters)
    return _stacked_practitioner_revenue_chart(rows)


def _stacked_practitioner_revenue_chart(rows):
    grouped = defaultdict(lambda: defaultdict(float))
    for row in rows:
        practitioner = cstr(row.get("practitioner") or "").strip()
        if not practitioner:
            continue
        branch = cstr(row.get("branch") or _("Unassigned")).strip() or _("Unassigned")
        grouped[practitioner][branch] += flt(row.get("revenue_linked_to_consultations"))

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


def _dashboard_report_links(key):
    links = {
        "executive": ["Consultation Register", "Revenue Summary", "Branch Performance Report"],
        "clinical": ["Consultation Register", "Lab Order Report", "Vaccination Report"],
        "financial": ["Revenue Summary", "Unpaid Invoice Report"],
        "practitioner_performance": ["Practitioner Performance Report", "Consultation Register"],
        "branch_performance": ["Branch Performance Report", "Revenue Summary"],
        "inventory_dispensary": ["Dispensary Activity Report", "Stock Usage Summary"],
        "lab": ["Lab Order Report"],
        "vaccination": ["Vaccination Report"],
        "boarding": ["Boarding Report", "Kennel Availability Report"],
        "grooming": ["Grooming Report"],
    }
    return [{"label": label, "report": label} for label in links.get(key, [])]


def _vaccination_due_counts(rows):
    due_soon = 0
    overdue = 0
    for row in rows:
        state = _vaccination_due_state(row.get("next_due_date"), row.get("status"))
        if state == "Due Soon":
            due_soon += 1
        if state == "Overdue":
            overdue += 1
    return due_soon, overdue


def _vaccination_due_state(next_due_date, status):
    if cstr(status) != "Administered" or not next_due_date:
        return "Administered" if cstr(status) == "Administered" else ""
    due_date = getdate(next_due_date)
    today = getdate(nowdate())
    if due_date < today:
        return "Overdue"
    if due_date <= add_days(today, 30):
        return "Due Soon"
    return "Administered"


def _active_boarding_stays_count(branch=None):
    if not frappe.db.exists("DocType", "Pet Boarding Stay"):
        return 0
    filters = {}
    status_field = _existing_field("Pet Boarding Stay", ["status"])
    branch_field = _existing_field("Pet Boarding Stay", ["service_branch", "branch"])
    if status_field:
        filters[status_field] = "Active"
    if branch and branch_field:
        filters[branch_field] = branch
    return cint(frappe.db.count("Pet Boarding Stay", filters))


def _boarding_occupancy_snapshot(branch=None):
    if not frappe.db.exists("DocType", "Kennel"):
        return {"occupied": 0, "capacity": 0, "display": "0 / 0"}
    kennel_filters = {}
    branch_field = _existing_field("Kennel", ["branch"])
    active_field = _existing_field("Kennel", ["is_active"])
    if branch and branch_field:
        kennel_filters[branch_field] = branch
    if active_field:
        kennel_filters[active_field] = 1
    capacity = sum(flt(row.get("capacity") or 1) for row in frappe.get_all("Kennel", filters=kennel_filters, fields=["capacity"]))
    occupied = _active_boarding_stays_count(branch)
    display = f"{cint(occupied)} / {cint(capacity)}"
    if capacity:
        display = f"{display} ({flt((occupied / capacity) * 100, 1)}%)"
    return {"occupied": occupied, "capacity": capacity, "display": display}


def _expected_checkouts_today(branch=None):
    if not frappe.db.exists("DocType", "Pet Boarding Booking"):
        return 0
    filters = {"expected_check_out_date": nowdate()}
    branch_field = _existing_field("Pet Boarding Booking", ["service_branch", "branch"])
    if branch and branch_field:
        filters[branch_field] = branch
    return cint(frappe.db.count("Pet Boarding Booking", filters))


def _sum_grooming_revenue(rows):
    return sum(flt(row.get("total_charge")) for row in rows)


def _active_patient_count():
    if not frappe.db.exists("DocType", "Veterinary Patient"):
        return 0
    status_field = _existing_field("Veterinary Patient", ["status"])
    if not status_field:
        return cint(frappe.db.count("Veterinary Patient"))
    return cint(
        frappe.db.count(
            "Veterinary Patient",
            {status_field: ("not in", ["Inactive", "Deceased", "Archived"])},
        )
    )


def _count_status(rows, statuses):
    statuses = {cstr(status) for status in statuses}
    return sum(1 for row in rows if cstr(row.get("status")) in statuses)


def _date_filter_dict(fieldname, filters, default_days=None):
    query_filters = {}
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if not from_date and not to_date and default_days:
        to_date = nowdate()
        from_date = add_days(to_date, -cint(default_days))
    if from_date:
        query_filters[fieldname] = (">=", from_date)
    if to_date:
        existing = query_filters.get(fieldname)
        if existing:
            query_filters[fieldname] = ("between", [from_date, to_date])
        else:
            query_filters[fieldname] = ("<=", to_date)
    return query_filters


def _existing_field(doctype, candidates):
    if not frappe.db.exists("DocType", doctype):
        return None
    meta = frappe.get_meta(doctype)
    for fieldname in candidates:
        if fieldname in STANDARD_FIELDS or meta.get_field(fieldname):
            return fieldname
    return None


def _invoice_status_from_row(row):
    docstatus = cint(row.get("docstatus"))
    outstanding = flt(row.get("outstanding_amount"))
    if docstatus == 0:
        return "Draft"
    if docstatus == 2:
        return "Cancelled"
    if outstanding <= 0:
        return "Paid"
    return "Unpaid"


def _infer_service_category(description, item_code):
    haystack = f"{cstr(description)} {cstr(item_code)}".lower()
    if "vaccin" in haystack:
        return "Vaccination"
    if "board" in haystack or "kennel" in haystack:
        return "Boarding"
    if "groom" in haystack:
        return "Grooming"
    if "lab" in haystack:
        return "Lab"
    if "dispens" in haystack or "pharmacy" in haystack or "drug" in haystack:
        return "Dispensary"
    if "consult" in haystack or "exam" in haystack:
        return "Consultation"
    if "registration" in haystack:
        return "Registration"
    return ""


def _col(fieldname, fieldtype="Data", options=None, label=None):
    column = {"fieldname": fieldname, "label": label or frappe.unscrub(fieldname), "fieldtype": fieldtype, "width": 160}
    if options:
        column["options"] = options
    return column


def _chart(title, chart_type, labels, values, color):
    return {
        "data": {"labels": labels, "datasets": [{"name": title, "values": values}]},
        "type": chart_type,
        "colors": [color],
        "barOptions": {"stacked": 0},
        "title": title,
    }


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
