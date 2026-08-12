from __future__ import annotations

from collections import defaultdict

import frappe
from frappe.utils import cint, cstr, flt

from vetedge.services.reporting_structure import _col, _existing_field


def execute_owner_register(filters=None):
    """Build Owner Register while limiting dependent aggregates to visible owners.

    Branch filtering determines which owners are visible, but pet counts retain the
    established report meaning: all pets belonging to each visible owner are counted,
    regardless of the patient's branch.
    """
    filters = frappe._dict(filters or {})
    customer_fields = ["name", "customer_name"]
    phone_field = _existing_field("Customer", ["mobile_no", "phone", "phone_number"])
    email_field = _existing_field("Customer", ["email_id", "email"])
    for fieldname in (phone_field, email_field):
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

    customers = frappe.get_all(
        "Customer",
        filters=query_filters,
        fields=customer_fields,
        order_by="customer_name asc",
    )
    visible_customer_names = sorted(
        {
            cstr(customer.name).strip()
            for customer in customers
            if cstr(customer.name).strip()
            and (branch_owner_names is None or cstr(customer.name).strip() in branch_owner_names)
        }
    )

    pet_counts = defaultdict(int)
    if visible_customer_names and frappe.db.exists("DocType", "Veterinary Patient"):
        owner_field = _existing_field("Veterinary Patient", ["primary_owner", "owner"])
        if owner_field:
            for row in frappe.get_all(
                "Veterinary Patient",
                filters={owner_field: ("in", visible_customer_names)},
                fields=[owner_field, {"COUNT": "name", "as": "pet_count"}],
                group_by=owner_field,
            ):
                pet_counts[row.get(owner_field)] = cint(row.get("pet_count"))

    outstanding = defaultdict(float)
    if visible_customer_names:
        invoice_filters = {
            "docstatus": 1,
            "outstanding_amount": (">", 0),
            "customer": ("in", visible_customer_names),
        }
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
        customer_name = cstr(customer.name).strip()
        if customer_name not in visible_customer_names:
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
