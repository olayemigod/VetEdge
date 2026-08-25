from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters
from vetedge.services.reporting_structure import _existing_field


DOCTYPE = "Customer"
PATIENT_DOCTYPE = "Veterinary Patient"
PAGE_LENGTH_MAX = 100
SORT_FIELDS = {
    "owner": "c.`name`",
    "customer_name": "c.`customer_name`",
}
DEFAULT_SORT = {"field": "customer_name", "direction": "asc"}


def _filters(value: str | dict | None) -> dict:
    if not value:
        value = {}
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    if cleaned.get("customer") and not cleaned.get("owner"):
        cleaned["owner"] = cleaned.get("customer")
    return dict(normalize_report_filters("Owner Register", cleaned) or {})


def _normalize_sort(value: str | dict | None) -> dict:
    if not value:
        return dict(DEFAULT_SORT)
    parsed = value if isinstance(value, dict) else frappe.parse_json(value)
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected report sort as a JSON object."), frappe.ValidationError)
    field = cstr(parsed.get("field") or parsed.get("fieldname") or parsed.get("key")).strip()
    direction = cstr(parsed.get("direction") or parsed.get("order")).strip().lower()
    if field not in SORT_FIELDS or direction not in {"asc", "desc"}:
        return dict(DEFAULT_SORT)
    return {"field": field, "direction": direction}


def _order_by(sort: dict) -> str:
    field = sort.get("field") if sort.get("field") in SORT_FIELDS else DEFAULT_SORT["field"]
    direction = "ASC" if sort.get("direction") == "asc" else "DESC"
    source = SORT_FIELDS[field]
    if field == "owner":
        return f"{source} {direction}"
    return f"{source} {direction}, c.`name` {direction}"


def _require_read_permission() -> None:
    if not frappe.has_permission(DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view owners."), frappe.PermissionError)


def _patient_fields() -> tuple[str | None, str | None]:
    if not frappe.db.exists("DocType", PATIENT_DOCTYPE):
        return None, None
    owner_field = _existing_field(PATIENT_DOCTYPE, ["primary_owner", "owner"])
    branch_field = _existing_field(PATIENT_DOCTYPE, ["default_branch", "branch", "service_branch"])
    return owner_field, branch_field


def _customer_contact_fields() -> tuple[str | None, str | None]:
    phone = _existing_field(DOCTYPE, ["mobile_no", "phone", "phone_number"])
    email = _existing_field(DOCTYPE, ["email_id", "email"])
    return phone, email


def _invoice_branch_field() -> str | None:
    if not frappe.db.exists("DocType", "Sales Invoice"):
        return None
    return _existing_field("Sales Invoice", ["branch", "service_branch"])


def _where_clause(report_filters: dict) -> tuple[str, dict]:
    params: dict = {}
    conditions = []
    owner = cstr(report_filters.get("owner") or "").strip()
    if owner:
        params["owner"] = owner
        conditions.append("c.`name` = %(owner)s")

    branch = cstr(report_filters.get("branch") or "").strip()
    patient_owner_field, patient_branch_field = _patient_fields()
    if branch and patient_owner_field and patient_branch_field:
        params["branch"] = branch
        conditions.append(
            f"EXISTS (SELECT 1 FROM `tab{PATIENT_DOCTYPE}` p WHERE p.`{patient_owner_field}` = c.`name` AND p.`{patient_branch_field}` = %(branch)s LIMIT 1)"
        )

    if cint(report_filters.get("outstanding_only")):
        invoice_branch = _invoice_branch_field()
        invoice_branch_clause = ""
        if branch and invoice_branch:
            params["invoice_branch"] = branch
            invoice_branch_clause = f" AND si.`{invoice_branch}` = %(invoice_branch)s"
        conditions.append(
            "EXISTS (SELECT 1 FROM `tabSales Invoice` si WHERE si.`customer` = c.`name` AND si.`docstatus` = 1 AND si.`outstanding_amount` > 0"
            + invoice_branch_clause
            + " LIMIT 1)"
        )

    return (" AND ".join(conditions) if conditions else "1=1"), params


def _columns() -> list[dict]:
    columns = [
        {"fieldname": "owner", "label": _("Owner"), "fieldtype": "Link", "options": DOCTYPE},
        {"fieldname": "customer_name", "label": _("Customer Name"), "fieldtype": "Data"},
        {"fieldname": "phone", "label": _("Phone"), "fieldtype": "Data"},
        {"fieldname": "email", "label": _("Email"), "fieldtype": "Data"},
        {"fieldname": "number_of_pets", "label": _("Number of Pets"), "fieldtype": "Int"},
        {"fieldname": "outstanding_amount", "label": _("Outstanding Amount"), "fieldtype": "Currency"},
    ]
    for column in columns:
        column["sortable"] = column.get("fieldname") in SORT_FIELDS
    return columns


def _count_rows(where_sql: str, params: dict) -> int:
    rows = frappe.db.sql(
        f"SELECT COUNT(*) AS `row_count` FROM `tabCustomer` c WHERE {where_sql}",
        params,
        as_dict=True,
    )
    return cint(rows[0].get("row_count")) if rows else 0


def _page_customers(where_sql: str, params: dict, start: int, page_length: int, sort: dict):
    phone_field, email_field = _customer_contact_fields()
    phone_select = f"c.`{phone_field}` AS `phone`" if phone_field else "'' AS `phone`"
    email_select = f"c.`{email_field}` AS `email`" if email_field else "'' AS `email`"
    page_params = dict(params)
    page_params.update({"limit": page_length, "offset": start})
    order_by = _order_by(sort)
    return frappe.db.sql(
        f"""
        SELECT c.`name`, c.`customer_name`, {phone_select}, {email_select}
        FROM `tabCustomer` c
        WHERE {where_sql}
        ORDER BY {order_by}
        LIMIT %(limit)s OFFSET %(offset)s
        """,
        page_params,
        as_dict=True,
    )


def _page_pet_counts(owner_names: list[str]) -> dict[str, int]:
    owner_field, _branch_field = _patient_fields()
    if not owner_names or not owner_field:
        return {}
    rows = frappe.get_all(
        PATIENT_DOCTYPE,
        filters={owner_field: ("in", owner_names)},
        fields=[owner_field, {"COUNT": "name", "as": "pet_count"}],
        group_by=owner_field,
    )
    return {row.get(owner_field): cint(row.get("pet_count")) for row in rows}


def _page_outstanding(owner_names: list[str], branch: str | None) -> dict[str, float]:
    if not owner_names or not frappe.db.exists("DocType", "Sales Invoice"):
        return {}
    filters: dict = {"customer": ("in", owner_names), "docstatus": 1, "outstanding_amount": (">", 0)}
    branch_field = _invoice_branch_field()
    if branch and branch_field:
        filters[branch_field] = branch
    rows = frappe.get_all(
        "Sales Invoice",
        filters=filters,
        fields=["customer", {"SUM": "outstanding_amount", "as": "outstanding_amount"}],
        group_by="customer",
    )
    return {row.get("customer"): flt(row.get("outstanding_amount")) for row in rows}


def _summary(where_sql: str, params: dict, total: int, branch: str | None) -> list[dict]:
    owner_field, _branch_field = _patient_fields()
    pet_count = 0
    if owner_field:
        rows = frappe.db.sql(
            f"""
            SELECT COUNT(p.`name`) AS `pet_count`
            FROM `tab{PATIENT_DOCTYPE}` p
            INNER JOIN `tabCustomer` c ON c.`name` = p.`{owner_field}`
            WHERE {where_sql}
            """,
            params,
            as_dict=True,
        )
        pet_count = cint(rows[0].get("pet_count")) if rows else 0

    outstanding_params = dict(params)
    invoice_branch = _invoice_branch_field()
    invoice_branch_clause = ""
    if branch and invoice_branch:
        outstanding_params["summary_invoice_branch"] = branch
        invoice_branch_clause = f" AND si.`{invoice_branch}` = %(summary_invoice_branch)s"
    outstanding_rows = frappe.db.sql(
        f"""
        SELECT COUNT(DISTINCT c.`name`) AS `owners_owing`, SUM(si.`outstanding_amount`) AS `outstanding_amount`
        FROM `tabCustomer` c
        INNER JOIN `tabSales Invoice` si ON si.`customer` = c.`name`
        WHERE {where_sql} AND si.`docstatus` = 1 AND si.`outstanding_amount` > 0{invoice_branch_clause}
        """,
        outstanding_params,
        as_dict=True,
    ) if frappe.db.exists("DocType", "Sales Invoice") else []
    outstanding_row = outstanding_rows[0] if outstanding_rows else {}
    return [
        {"label": _("Owners"), "value": total, "indicator": "Blue", "datatype": "Int"},
        {"label": _("Pets"), "value": pet_count, "indicator": "Green", "datatype": "Int"},
        {"label": _("Owners Owing"), "value": cint(outstanding_row.get("owners_owing")), "indicator": "Orange", "datatype": "Int"},
        {"label": _("Outstanding Amount"), "value": flt(outstanding_row.get("outstanding_amount")), "indicator": "Orange", "datatype": "Currency"},
    ]


@frappe.whitelist()
@frappe.read_only()
def get_owner_register_view(
    filters: str | dict | None = None,
    start: int = 0,
    page_length: int = 50,
    sort: str | dict | None = None,
) -> dict:
    require_internal_user()
    _require_read_permission()
    report_filters = _filters(filters)
    where_sql, params = _where_clause(report_filters)
    normalized_sort = _normalize_sort(sort)
    start = max(cint(start), 0)
    page_length = min(max(cint(page_length) or 50, 1), PAGE_LENGTH_MAX)
    total = _count_rows(where_sql, params)
    customers = _page_customers(where_sql, params, start, page_length, normalized_sort)
    owner_names = [row.get("name") for row in customers if row.get("name")]
    pet_counts = _page_pet_counts(owner_names)
    outstanding = _page_outstanding(owner_names, report_filters.get("branch"))
    rows = [
        {
            "owner": row.get("name"),
            "customer_name": row.get("customer_name"),
            "phone": row.get("phone"),
            "email": row.get("email"),
            "number_of_pets": cint(pet_counts.get(row.get("name"))),
            "outstanding_amount": flt(outstanding.get(row.get("name"))),
        }
        for row in customers
    ]
    return {
        "title": _("Owner Register"),
        "columns": _columns(),
        "rows": rows,
        "summary": _summary(where_sql, params, total, report_filters.get("branch")),
        "chart": None,
        "message": "",
        "total": total,
        "start": start,
        "page_length": page_length,
        "sort": normalized_sort,
        "metadata": {
            "pagination_mode": "query-level",
            "sorting_mode": "server-allowlist",
            "detail_rows_materialized": False,
            "enrichment_mode": "page-only",
            "summary_mode": "database-aggregate",
            "branch_visibility_semantics": "owners-with-patient-in-branch",
            "pet_count_semantics": "all-pets-for-visible-owner",
            "source": "owner-register",
        },
    }
