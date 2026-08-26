from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate

from vetedge.services.nadis_template_loader import load_verified_template_bytes
from vetedge.services.nadis_templates import (
    ANIMAL_SEX_VALUES,
    CONTROL_MEASURE_FLAGS,
    DIAGNOSIS_BASES,
    DISEASE_OUTBREAK_TEMPLATE_FILENAME,
    DISEASE_OUTBREAK_TEMPLATE_SHA256,
    EPIDEMIOLOGICAL_UNIT_TYPES,
    OUTBREAK_DATA_START_ROW,
    OUTBREAK_SHEET_DEFINITIONS,
    OUTBREAK_SHEETS,
    OUTBREAK_STATUSES,
    OUTBREAK_TYPES,
    PRODUCTION_SYSTEMS,
)
from vetedge.services.nadis_xlsx_template_writer import populate_official_template
from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_visibility import normalize_report_filters

OUTBREAK_DOCTYPE = "Veterinary Disease Outbreak"
ANIMAL_GROUP_DOCTYPE = "Veterinary Outbreak Animal Group"
DIAGNOSIS_BASIS_DOCTYPE = "Veterinary Outbreak Diagnosis Basis"
CONTROL_MEASURE_DOCTYPE = "Veterinary Outbreak Control Measure"
LOCATION_DOCTYPE = "Veterinary Outbreak Location"
MAX_TEMPLATE_ROWS = 248  # official workbook entry areas use rows 5:252


def _filters(value: str | dict | None) -> dict:
    parsed = value if isinstance(value, dict) else frappe.parse_json(value) if value else {}
    if not isinstance(parsed, dict):
        frappe.throw(_("Expected disease-outbreak filters as a JSON object."), frappe.ValidationError)
    cleaned = {key: item for key, item in parsed.items() if item not in (None, "")}
    return dict(normalize_report_filters("NADIS Disease Outbreak Report", cleaned) or {})


def _require_permissions() -> None:
    require_internal_user()
    if not frappe.has_permission(OUTBREAK_DOCTYPE, "read"):
        frappe.throw(_("You do not have permission to view Veterinary Disease Outbreak records."), frappe.PermissionError)


def _query_filters(filters: dict) -> dict:
    result = {}
    if filters.get("branch"):
        result["service_branch"] = filters["branch"]
    if filters.get("company"):
        result["company"] = filters["company"]
    if filters.get("status"):
        result["outbreak_status"] = filters["status"]
    if filters.get("disease"):
        result["disease"] = filters["disease"]
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    if from_date and to_date:
        result["date_investigated"] = ["between", [from_date, to_date]]
    elif from_date:
        result["date_investigated"] = [">=", from_date]
    elif to_date:
        result["date_investigated"] = ["<=", to_date]
    return result


def _fetch_parents(query_filters: dict) -> list[dict]:
    total = cint(frappe.db.count(OUTBREAK_DOCTYPE, filters=query_filters))
    if total > MAX_TEMPLATE_ROWS:
        frappe.throw(
            _("The official outbreak workbook supports at most {0} outbreak rows for one export; this selection contains {1}. Narrow the filters.").format(MAX_TEMPLATE_ROWS, total),
            frappe.ValidationError,
        )
    return frappe.get_list(
        OUTBREAK_DOCTYPE,
        filters=query_filters,
        fields=[
            "name", "country", "admin_level_1", "disease", "nadis_disease", "serotype",
            "outbreak_type", "parent_outbreak", "number_new_outbreaks", "total_outbreaks",
            "date_outbreak_started", "date_reported_to_vet", "date_investigated",
            "date_final_diagnosis", "source_of_infection", "outbreak_status", "service_branch", "company",
        ],
        order_by="date_investigated asc, name asc",
        page_length=max(total, 1),
    )


def _child_rows(doctype: str, parent_names: list[str], fields: list[str]) -> list[dict]:
    if not parent_names:
        return []
    rows = frappe.get_list(
        doctype,
        filters={"parent": ["in", parent_names], "parenttype": OUTBREAK_DOCTYPE},
        fields=["parent", "idx", *fields],
        order_by="parent asc, idx asc",
        page_length=MAX_TEMPLATE_ROWS + 1,
    )
    if len(rows) > MAX_TEMPLATE_ROWS:
        frappe.throw(
            _("The official NADIS child sheets support at most {0} rows per export. Narrow the selected outbreak set.").format(MAX_TEMPLATE_ROWS),
            frappe.ValidationError,
        )
    return rows


def _validation(parent_rows: list[dict], animals: list[dict], diagnoses: list[dict], controls: list[dict], locations: list[dict]) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    animals_by_parent: dict[str, list[dict]] = {}
    diagnoses_by_parent: dict[str, list[dict]] = {}
    controls_by_parent: dict[str, list[dict]] = {}
    locations_by_parent: dict[str, list[dict]] = {}
    for collection, target in (
        (animals, animals_by_parent), (diagnoses, diagnoses_by_parent),
        (controls, controls_by_parent), (locations, locations_by_parent),
    ):
        for row in collection:
            target.setdefault(row.get("parent"), []).append(row)

    for row in parent_rows:
        name = row.get("name")
        missing = []
        if not row.get("country"):
            missing.append("Country")
        if not row.get("admin_level_1"):
            missing.append("Admin Level 1")
        if not row.get("nadis_disease"):
            missing.append("NADIS Disease")
        if not row.get("date_investigated"):
            missing.append("Date Investigated")
        if not row.get("date_final_diagnosis"):
            missing.append("Date of Final Diagnosis")
        if missing:
            errors.append({"record": name, "message": _("Missing required NADIS outbreak data: {0}").format(", ".join(missing))})
        if row.get("outbreak_type") not in OUTBREAK_TYPES:
            errors.append({"record": name, "message": _("New/Follow-up classification does not match the supplied NADIS template.")})
        if row.get("outbreak_status") not in OUTBREAK_STATUSES:
            errors.append({"record": name, "message": _("Outbreak Status must be Continuing or Resolved.")})
        if row.get("outbreak_type") == "Follow up outbreak" and not row.get("parent_outbreak"):
            errors.append({"record": name, "message": _("Follow-up outbreak is missing its Original Outbreak link.")})
        if cint(row.get("number_new_outbreaks")) < 0:
            errors.append({"record": name, "message": _("Number of New Outbreaks cannot be negative.")})
        if row.get("outbreak_type") == "New outbreak" and cint(row.get("number_new_outbreaks")) < 1:
            errors.append({"record": name, "message": _("A New outbreak must report at least one new outbreak; use Follow up outbreak when no new outbreak occurred.")})
        if cint(row.get("total_outbreaks")) < 0:
            errors.append({"record": name, "message": _("Total Number of Outbreaks cannot be negative.")})
        if not animals_by_parent.get(name):
            errors.append({"record": name, "message": _("At least one Animals Affected row is required for NADIS export.")})
        if not locations_by_parent.get(name):
            errors.append({"record": name, "message": _("At least one affected Location is required for NADIS export.")})
        if not diagnoses_by_parent.get(name):
            warnings.append({"record": name, "message": _("No Basis of Diagnosis row is recorded.")})
        if not controls_by_parent.get(name):
            warnings.append({"record": name, "message": _("No Disease Control Measure is recorded.")})

    for row in animals:
        parent = row.get("parent")
        if not row.get("nadis_species"):
            errors.append({"record": parent, "message": _("Animals Affected row {0} is missing its NADIS Species mapping.").format(row.get("idx"))})
        if cint(row.get("number_cases")) < 1:
            errors.append({"record": parent, "message": _("Animals Affected row {0} must have at least one case.").format(row.get("idx"))})
        for fieldname in (
            "number_susceptible", "number_cases", "number_deaths", "number_slaughtered",
            "number_destroyed", "number_vaccinated_around_outbreak",
        ):
            if cint(row.get(fieldname)) < 0:
                errors.append({"record": parent, "message": _("Animals Affected row {0} contains a negative count.").format(row.get("idx"))})
        if cint(row.get("number_deaths")) > cint(row.get("number_cases")):
            errors.append({"record": parent, "message": _("Animals Affected row {0} has more Deaths than Cases.").format(row.get("idx"))})
        if row.get("sex") and row.get("sex") not in ANIMAL_SEX_VALUES:
            errors.append({"record": parent, "message": _("Animals Affected row {0} has an unsupported Sex value.").format(row.get("idx"))})

    for row in diagnoses:
        if row.get("basis_of_diagnosis") not in DIAGNOSIS_BASES:
            errors.append({"record": row.get("parent"), "message": _("Basis of Diagnosis row {0} does not match the official template values.").format(row.get("idx"))})
    for row in controls:
        if not row.get("control_measure") or row.get("flag") not in CONTROL_MEASURE_FLAGS:
            errors.append({"record": row.get("parent"), "message": _("Disease Control Measure row {0} is incomplete.").format(row.get("idx"))})
    for row in locations:
        parent = row.get("parent")
        if not row.get("locality_name"):
            errors.append({"record": parent, "message": _("Location row {0} is missing Name of Locality.").format(row.get("idx"))})
        if row.get("epidemiological_unit_type") and row.get("epidemiological_unit_type") not in EPIDEMIOLOGICAL_UNIT_TYPES:
            errors.append({"record": parent, "message": _("Location row {0} has an unsupported Epidemiological Unit Type.").format(row.get("idx"))})
        if row.get("production_system") and row.get("production_system") not in PRODUCTION_SYSTEMS:
            errors.append({"record": parent, "message": _("Location row {0} has an unsupported Production System.").format(row.get("idx"))})
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        if latitude not in (None, "") and not -90 <= flt(latitude) <= 90:
            errors.append({"record": parent, "message": _("Location row {0} has Latitude outside -90 to 90.").format(row.get("idx"))})
        if longitude not in (None, "") and not -180 <= flt(longitude) <= 180:
            errors.append({"record": parent, "message": _("Location row {0} has Longitude outside -180 to 180.").format(row.get("idx"))})
    return {"errors": errors, "warnings": warnings}


def _dataset(filters: str | dict | None = None) -> dict:
    _require_permissions()
    report_filters = _filters(filters)
    parents = _fetch_parents(_query_filters(report_filters))
    names = [row.get("name") for row in parents]
    animals = _child_rows(
        ANIMAL_GROUP_DOCTYPE,
        names,
        ["nadis_species", "age_group", "sex", "number_susceptible", "number_cases", "number_deaths", "number_slaughtered", "number_destroyed", "number_vaccinated_around_outbreak"],
    )
    diagnoses = _child_rows(DIAGNOSIS_BASIS_DOCTYPE, names, ["basis_of_diagnosis"])
    controls = _child_rows(CONTROL_MEASURE_DOCTYPE, names, ["control_measure", "flag"])
    locations = _child_rows(LOCATION_DOCTYPE, names, ["locality_name", "epidemiological_unit_type", "production_system", "latitude", "longitude"])
    validation = _validation(parents, animals, diagnoses, controls, locations)
    return {
        "parents": parents,
        "animals": animals,
        "diagnoses": diagnoses,
        "controls": controls,
        "locations": locations,
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "template_mapping_verified": True,
        "template_filename": DISEASE_OUTBREAK_TEMPLATE_FILENAME,
        "template_sha256": DISEASE_OUTBREAK_TEMPLATE_SHA256,
        "submission_ready": bool(parents) and not validation["errors"],
    }


@frappe.whitelist()
@frappe.read_only()
def validate_nadis_outbreak_export(filters: str | dict | None = None) -> dict:
    data = _dataset(filters)
    return {
        "outbreak_count": len(data["parents"]),
        "animal_group_count": len(data["animals"]),
        "diagnosis_basis_count": len(data["diagnoses"]),
        "control_measure_count": len(data["controls"]),
        "location_count": len(data["locations"]),
        "errors": data["errors"][:200],
        "warnings": data["warnings"][:200],
        "error_count": len(data["errors"]),
        "warning_count": len(data["warnings"]),
        "template_mapping_verified": True,
        "template_filename": data["template_filename"],
        "template_sha256": data["template_sha256"],
        "submission_ready": data["submission_ready"],
    }


def _sheet_rows(data: dict) -> dict[str, list[list]]:
    outbreak_rows: list[list] = []
    for row in data["parents"]:
        investigated = getdate(row.get("date_investigated"))
        outbreak_rows.append([
            None,
            row.get("name"),
            row.get("country"),
            row.get("admin_level_1"),
            investigated.year,
            investigated.strftime("%B"),
            row.get("nadis_disease"),
            row.get("serotype"),
            row.get("outbreak_type"),
            cint(row.get("number_new_outbreaks")),
            cint(row.get("total_outbreaks")),
            getdate(row.get("date_outbreak_started")) if row.get("date_outbreak_started") else None,
            getdate(row.get("date_reported_to_vet")) if row.get("date_reported_to_vet") else None,
            investigated,
            getdate(row.get("date_final_diagnosis")),
            row.get("source_of_infection"),
            row.get("outbreak_status"),
        ])

    return {
        "Outbreaks": outbreak_rows,
        "Animals affected": [[
            None, row.get("parent"), row.get("nadis_species"), row.get("age_group"), row.get("sex"),
            cint(row.get("number_susceptible")), cint(row.get("number_cases")), cint(row.get("number_deaths")),
            cint(row.get("number_slaughtered")), cint(row.get("number_destroyed")), cint(row.get("number_vaccinated_around_outbreak")),
        ] for row in data["animals"]],
        "Bases of Diagnosis": [[None, row.get("parent"), row.get("basis_of_diagnosis")] for row in data["diagnoses"]],
        "Disease Control Measures": [[None, row.get("parent"), row.get("control_measure"), row.get("flag")] for row in data["controls"]],
        "Locations": [[
            None, row.get("parent"), row.get("locality_name"), row.get("epidemiological_unit_type"),
            row.get("production_system"), row.get("latitude"), row.get("longitude"),
        ] for row in data["locations"]],
    }


def _build_workbook(data: dict) -> bytes:
    template_bytes = load_verified_template_bytes(DISEASE_OUTBREAK_TEMPLATE_FILENAME)
    column_counts = {
        sheet_name: len(OUTBREAK_SHEET_DEFINITIONS[sheet_name].get("field_ids") or ())
        for sheet_name in OUTBREAK_SHEETS
    }
    return populate_official_template(
        template_bytes,
        sheet_rows=_sheet_rows(data),
        start_row=OUTBREAK_DATA_START_ROW,
        visible_column_counts=column_counts,
        clear_through_row=OUTBREAK_DATA_START_ROW + MAX_TEMPLATE_ROWS - 1,
    )


@frappe.whitelist()
def download_nadis_outbreak_workbook(filters: str | dict | None = None):
    data = _dataset(filters)
    if not data["submission_ready"]:
        messages = [item.get("message") for item in data["errors"][:10]]
        frappe.throw(
            _("NADIS Disease Outbreak export is blocked until required regulatory data is complete.{0}").format("\n" + "\n".join(messages) if messages else ""),
            frappe.ValidationError,
        )

    report_filters = _filters(filters)
    from_date = cstr(report_filters.get("from_date")).strip()
    to_date = cstr(report_filters.get("to_date")).strip()
    suffix = ""
    if from_date or to_date:
        suffix = "_" + "_to_".join(value for value in (from_date, to_date) if value)
    frappe.local.response.filename = f"NADIS_Disease_Outbreak_Report{suffix}.xlsx"
    frappe.local.response.filecontent = _build_workbook(data)
    frappe.local.response.type = "binary"
    frappe.local.response.display_content_as = "attachment"
