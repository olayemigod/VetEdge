from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now_datetime

from vetedge.services.hospitalisation_permissions import validate_hospitalisation_branch_access
from vetedge.services.portal_access import require_internal_user


HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
SETTINGS_DOCTYPE = "Veterinary Settings"
ITEM_REQUIRED_ACTIVITY_TYPES = {"Medication", "Fluid Therapy"}
CHARGE_EDIT_FIELDS = {"item", "qty", "uom", "rate", "description"}


def _clean(value: Any) -> str:
    return cstr(value or "").strip()


def _setting_enabled(fieldname: str, default: bool) -> bool:
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        return default
    meta = frappe.get_meta(SETTINGS_DOCTYPE)
    if not meta.has_field(fieldname):
        return default
    value = frappe.db.get_single_value(SETTINGS_DOCTYPE, fieldname)
    if value is None:
        return default
    return bool(cint(value))


def is_hospitalisation_daily_charges_enabled() -> bool:
    return _setting_enabled("enable_hospitalisation_daily_charges", True)


def is_hospitalisation_charge_editing_enabled() -> bool:
    return _setting_enabled("allow_editing_hospitalisation_charge_items", True)


def is_hospitalisation_dispensary_enabled() -> bool:
    if not frappe.db.exists("DocType", SETTINGS_DOCTYPE):
        return False
    try:
        from vetedge.services.feature_flags import is_enabled

        return bool(is_enabled("dispensary_flow"))
    except Exception:
        return False


def _load_hospitalisation(name: str, *, write: bool = False):
    require_internal_user()
    if not _clean(name):
        frappe.throw(_("Hospitalisation is required."), frappe.ValidationError)
    doc = frappe.get_doc(HOSPITALISATION_DOCTYPE, name)
    doc.check_permission("write" if write else "read")
    validate_hospitalisation_branch_access(doc)
    return doc


def _parse_payload(payload) -> dict[str, Any]:
    if isinstance(payload, str):
        payload = frappe.parse_json(payload)
    return payload if isinstance(payload, dict) else {}


def _assert_not_stale(doc, modified: str | None) -> None:
    if modified and cstr(doc.modified) != cstr(modified):
        frappe.throw(
            _("This Hospitalisation changed after the page was loaded. Refresh and try again."),
            frappe.TimestampMismatchError,
        )


def _invoice_state(invoice_name: str | None) -> dict[str, Any]:
    if not invoice_name or not frappe.db.exists("Sales Invoice", invoice_name):
        return {}
    return frappe.db.get_value(
        "Sales Invoice",
        invoice_name,
        ["docstatus", "status", "outstanding_amount"],
        as_dict=True,
    ) or {}


def _charge_editability(doc, row) -> tuple[bool, list[str], str]:
    if not is_hospitalisation_charge_editing_enabled():
        return False, [], _("Hospitalisation charge editing is disabled in Veterinary Settings.")
    if doc.get("status") == "Cancelled":
        return False, [], _("Cancelled Hospitalisation charges are read-only.")
    if not frappe.has_permission(HOSPITALISATION_DOCTYPE, ptype="write", doc=doc):
        return False, [], _("You do not have permission to edit this Hospitalisation.")

    invoice = _invoice_state(row.get("sales_invoice"))
    if invoice and cint(invoice.get("docstatus")) != 0:
        return False, [], _("This charge is linked to a submitted or cancelled Sales Invoice.")

    fields = ["qty", "rate"]
    if row.get("charge_category") not in {"Daily Stay"} and row.get("activity_type") != "Admission Fee":
        fields = ["item", "qty", "uom", "rate", "description"]
    return True, fields, ""


def _enrich_episode(payload: dict | None) -> dict:
    result = dict(payload or {})
    name = result.get("name")
    if not name:
        return result

    doc = _load_hospitalisation(name)
    dispensary_enabled = is_hospitalisation_dispensary_enabled()
    daily_enabled = is_hospitalisation_daily_charges_enabled()
    editing_enabled = is_hospitalisation_charge_editing_enabled()

    capabilities = dict(result.get("capabilities") or {})
    capabilities["dispensary_enabled"] = dispensary_enabled
    capabilities["daily_charges_enabled"] = daily_enabled
    capabilities["allow_charge_item_editing"] = editing_enabled
    capabilities["can_preview_stock"] = bool(capabilities.get("can_post_stock") and dispensary_enabled)
    capabilities["can_post_stock"] = bool(capabilities.get("can_post_stock") and dispensary_enabled)
    capabilities["can_generate_daily_charges"] = bool(capabilities.get("can_manage_charges") and daily_enabled)
    capabilities["can_edit_charge_items"] = bool(capabilities.get("can_write") and editing_enabled)
    result["capabilities"] = capabilities

    signals = dict(result.get("signals") or {})
    if not dispensary_enabled:
        signals["pending_stock"] = 0
    result["signals"] = signals

    row_by_name = {row.get("name"): row for row in (doc.get("charge_items") or []) if row.get("name")}
    enriched_charges = []
    for payload_row in result.get("charge_items") or []:
        row = row_by_name.get(payload_row.get("name"))
        enriched = dict(payload_row)
        if row:
            editable, fields, reason = _charge_editability(doc, row)
            enriched["editable"] = editable
            enriched["editable_fields"] = fields
            enriched["edit_block_reason"] = reason
            invoice = _invoice_state(row.get("sales_invoice"))
            enriched["invoice_docstatus"] = invoice.get("docstatus") if invoice else None
            enriched["invoice_is_draft"] = bool(invoice and cint(invoice.get("docstatus")) == 0)
        else:
            enriched["editable"] = False
            enriched["editable_fields"] = []
        enriched_charges.append(enriched)
    result["charge_items"] = enriched_charges
    return result


def _link_record_to_hospitalisation(doctype: str, name: str | None, hospitalisation_name: str) -> None:
    if not name or not frappe.db.exists(doctype, name):
        return
    meta = frappe.get_meta(doctype)
    if not meta.has_field("hospitalisation"):
        return
    current = frappe.db.get_value(doctype, name, "hospitalisation")
    if current and current != hospitalisation_name:
        frappe.throw(_("Clinical record is already linked to another Hospitalisation."), frappe.ValidationError)
    if current != hospitalisation_name:
        frappe.db.set_value(doctype, name, "hospitalisation", hospitalisation_name, update_modified=False)


def _link_activity_rows(hospitalisation_name: str, activity_names: list[str], doctype: str, document: str) -> None:
    if not activity_names:
        return
    doc = _load_hospitalisation(hospitalisation_name, write=True)
    changed = False
    wanted = set(activity_names)
    for row in doc.get("activities") or []:
        if row.get("name") not in wanted:
            continue
        row.linked_doctype = doctype
        row.linked_document = document
        changed = True
    if changed:
        doc.save()


def _normalize_unposted_stock_flags_when_dispensary_disabled(doc) -> bool:
    if is_hospitalisation_dispensary_enabled():
        return False
    changed = False
    for row in doc.get("activities") or []:
        if not cint(row.get("stock_affecting")):
            continue
        if row.get("stock_entry") or row.get("stock_status") == "Posted":
            continue
        row.stock_affecting = 0
        row.stock_status = "Not Applicable"
        row.source_warehouse = None
        row.stock_posting_message = _("Dispensary Flow is disabled in Veterinary Settings.")
        changed = True
    if changed:
        doc.save()
    return changed


def _daily_charge_disabled_result(name: str) -> dict[str, Any]:
    return {
        "hospitalisation": name,
        "created": 0,
        "updated": 0,
        "skipped_existing": 0,
        "missing_price": 0,
        "total_amount": 0,
        "disabled": True,
        "message": _("Hospitalisation Daily Charges are disabled in Veterinary Settings."),
    }


@frappe.whitelist()
def get_hospitalisation_episode(name: str) -> dict[str, Any]:
    from vetedge.services.hospitalisation_episode import get_hospitalisation_episode as original

    return _enrich_episode(original(name))


@frappe.whitelist()
def add_hospitalisation_activity(
    hospitalisation_name: str,
    activity_type: str,
    activity_datetime: str | None = None,
    clinical_notes: str | None = None,
    billable: int | str = 0,
    stock_affecting: int | str = 0,
    item: str | None = None,
    qty: float | str | None = None,
    uom: str | None = None,
    source_warehouse: str | None = None,
    modified: str | None = None,
) -> dict[str, Any]:
    from vetedge.services.hospitalisation_episode import add_hospitalisation_activity as original

    resolved_type = _clean(activity_type) or "Other"
    resolved_item = _clean(item)
    resolved_billable = cint(billable)
    resolved_stock = cint(stock_affecting)
    dispensary_enabled = is_hospitalisation_dispensary_enabled()

    if (resolved_billable or resolved_type in ITEM_REQUIRED_ACTIVITY_TYPES) and not resolved_item:
        frappe.throw(
            _("ERPNext Item is required for billable, Medication and Fluid Therapy Hospitalisation activities."),
            frappe.ValidationError,
        )
    if resolved_stock and not resolved_item:
        frappe.throw(_("ERPNext Item is required for a stock-affecting Hospitalisation activity."), frappe.ValidationError)
    if not dispensary_enabled:
        resolved_stock = 0
        source_warehouse = None

    result = original(
        hospitalisation_name=hospitalisation_name,
        activity_type=resolved_type,
        activity_datetime=activity_datetime,
        clinical_notes=clinical_notes,
        billable=resolved_billable,
        stock_affecting=resolved_stock,
        item=resolved_item or None,
        qty=qty,
        uom=uom,
        source_warehouse=source_warehouse,
        modified=modified,
    )
    if not dispensary_enabled and cint(stock_affecting):
        result.setdefault("warnings", []).append(
            _("Dispensary Flow is disabled, so this activity was recorded without stock posting.")
        )
    result["episode"] = _enrich_episode(result.get("episode"))
    return result


def _create_direct_hospitalisation_vitals(doc, values: dict[str, Any]) -> str:
    from vetedge.services.permissions import can_access_branch_data, get_current_user
    from vetedge.services.vitals import ensure_vitals_enabled

    ensure_vitals_enabled()
    if not frappe.has_permission("Veterinary Vital Signs", "create"):
        frappe.throw(_("Not permitted to create Veterinary Vital Signs."), frappe.PermissionError)
    can_access_branch_data(get_current_user(), doc.get("service_branch"), raise_exception=True)

    payload = {
        "doctype": "Veterinary Vital Signs",
        "patient": doc.get("patient"),
        "service_branch": doc.get("service_branch"),
        "recorded_by": get_current_user(),
        "recorded_on": values.get("recorded_on") or now_datetime(),
        "temperature": values.get("temperature"),
        "weight": values.get("weight"),
        "heart_rate": values.get("heart_rate"),
        "respiratory_rate": values.get("respiratory_rate"),
        "body_condition_score": values.get("body_condition_score"),
        "hydration_status": values.get("hydration_status"),
        "mucous_membrane": values.get("mucous_membrane"),
        "capillary_refill_time": values.get("capillary_refill_time"),
        "pain_score": values.get("pain_score"),
        "appetite_status": values.get("appetite_status"),
        "notes": values.get("notes"),
    }
    if frappe.get_meta("Veterinary Vital Signs").has_field("hospitalisation"):
        payload["hospitalisation"] = doc.name
    record = frappe.get_doc(payload)
    record.insert()
    return record.name


@frappe.whitelist()
def add_hospitalisation_vitals(hospitalisation_name: str, values=None, modified: str | None = None) -> dict[str, Any]:
    from vetedge.services.hospitalisation_episode import add_hospitalisation_vitals as original

    doc = _load_hospitalisation(hospitalisation_name, write=True)
    _assert_not_stale(doc, modified)
    payload = _parse_payload(values)
    direct_record = None
    if not doc.get("linked_consultation"):
        direct_record = _create_direct_hospitalisation_vitals(doc, payload)

    result = original(hospitalisation_name=hospitalisation_name, values=payload, modified=modified)
    linked_record = result.get("linked_record") or direct_record
    if linked_record:
        _link_record_to_hospitalisation("Veterinary Vital Signs", linked_record, hospitalisation_name)
        activity_name = (result.get("activity") or {}).get("name")
        if direct_record and activity_name:
            _link_activity_rows(hospitalisation_name, [activity_name], "Veterinary Vital Signs", linked_record)
        result["linked_record"] = linked_record
        result["episode"] = get_hospitalisation_episode(hospitalisation_name)
    return result


def _create_direct_hospitalisation_vaccination(doc, values: dict[str, Any]) -> str:
    from vetedge.services.permissions import get_current_user
    from vetedge.services.vaccination import ensure_vaccination_enabled

    ensure_vaccination_enabled()
    if not frappe.has_permission("Veterinary Vaccination Record", "create"):
        frappe.throw(_("Not permitted to create Veterinary Vaccination Record."), frappe.PermissionError)
    payload = {
        "doctype": "Veterinary Vaccination Record",
        "patient": doc.get("patient"),
        "primary_owner": doc.get("customer"),
        "service_branch": doc.get("service_branch"),
        "company": doc.get("company"),
        "vaccine": values.get("vaccine"),
        "dose": values.get("dose"),
        "route": values.get("route"),
        "notes": values.get("notes"),
        "administered_on": values.get("administered_on") or now_datetime(),
        "next_due_date": values.get("next_due_date"),
        "administered_by": None,
        "status": "Draft",
    }
    if frappe.get_meta("Veterinary Vaccination Record").has_field("hospitalisation"):
        payload["hospitalisation"] = doc.name
    record = frappe.get_doc(payload)
    record.insert()
    return record.name


@frappe.whitelist()
def add_hospitalisation_vaccination(hospitalisation_name: str, values=None, modified: str | None = None) -> dict[str, Any]:
    from vetedge.services.hospitalisation_episode import add_hospitalisation_vaccination as original

    doc = _load_hospitalisation(hospitalisation_name, write=True)
    _assert_not_stale(doc, modified)
    payload = _parse_payload(values)
    if not is_hospitalisation_dispensary_enabled():
        payload["stock_affecting"] = 0

    direct_record = None
    if not doc.get("linked_consultation"):
        direct_record = _create_direct_hospitalisation_vaccination(doc, payload)

    result = original(hospitalisation_name=hospitalisation_name, values=payload, modified=modified)
    linked_record = result.get("linked_record") or direct_record
    if linked_record:
        _link_record_to_hospitalisation("Veterinary Vaccination Record", linked_record, hospitalisation_name)
        activity_name = (result.get("activity") or {}).get("name")
        if direct_record and activity_name:
            _link_activity_rows(hospitalisation_name, [activity_name], "Veterinary Vaccination Record", linked_record)
        result["linked_record"] = linked_record
        result["episode"] = get_hospitalisation_episode(hospitalisation_name)
    if not is_hospitalisation_dispensary_enabled():
        result["warning"] = result.get("warning") or _(
            "Dispensary Flow is disabled; the Vaccination Record was created without Hospitalisation stock posting."
        )
    return result


def _create_direct_hospitalisation_lab_order(doc, lab_tests, sample_notes: str | None) -> str:
    from vetedge.services.lab import normalize_lab_tests_payload
    from vetedge.services.permissions import get_current_user

    if not frappe.has_permission("Veterinary Lab Order", "create"):
        frappe.throw(_("Not permitted to create Veterinary Lab Order."), frappe.PermissionError)
    rows = normalize_lab_tests_payload(lab_tests)
    if not rows:
        frappe.throw(_("Select at least one lab test."), frappe.ValidationError)
    payload = {
        "doctype": "Veterinary Lab Order",
        "patient": doc.get("patient"),
        "primary_owner": doc.get("customer"),
        "service_branch": doc.get("service_branch"),
        "requested_by": get_current_user(),
        "requested_on": now_datetime(),
        "status": "Ordered",
        "sample_notes": sample_notes,
        "lab_tests": rows,
    }
    if frappe.get_meta("Veterinary Lab Order").has_field("hospitalisation"):
        payload["hospitalisation"] = doc.name
    order = frappe.get_doc(payload)
    order.insert()
    return order.name


@frappe.whitelist()
def add_hospitalisation_lab_order(
    hospitalisation_name: str,
    lab_tests=None,
    sample_notes: str | None = None,
    modified: str | None = None,
) -> dict[str, Any]:
    from vetedge.services.hospitalisation_episode import add_hospitalisation_lab_order as original

    doc = _load_hospitalisation(hospitalisation_name, write=True)
    _assert_not_stale(doc, modified)
    before_names = {row.get("name") for row in doc.get("activities") or [] if row.get("name")}
    direct_order = None
    if not doc.get("linked_consultation"):
        direct_order = _create_direct_hospitalisation_lab_order(doc, lab_tests, sample_notes)

    result = original(
        hospitalisation_name=hospitalisation_name,
        lab_tests=lab_tests,
        sample_notes=sample_notes,
        modified=modified,
    )
    linked_order = result.get("linked_order") or direct_order
    if linked_order:
        _link_record_to_hospitalisation("Veterinary Lab Order", linked_order, hospitalisation_name)
        if direct_order:
            refreshed = _load_hospitalisation(hospitalisation_name)
            new_rows = [
                row.get("name")
                for row in refreshed.get("activities") or []
                if row.get("name") and row.get("name") not in before_names and row.get("activity_type") == "Lab"
            ]
            _link_activity_rows(hospitalisation_name, new_rows, "Veterinary Lab Order", linked_order)
        result["linked_order"] = linked_order
        result["episode"] = get_hospitalisation_episode(hospitalisation_name)
    return result


@frappe.whitelist()
def update_hospitalisation_charge_item(
    hospitalisation_name: str,
    charge_row_name: str,
    values=None,
    modified: str | None = None,
) -> dict[str, Any]:
    from vetedge.services import hospitalisation as service
    from vetedge.services.billing import validate_sales_item

    if not is_hospitalisation_charge_editing_enabled():
        frappe.throw(_("Hospitalisation charge editing is disabled in Veterinary Settings."), frappe.ValidationError)

    doc = _load_hospitalisation(hospitalisation_name, write=True)
    _assert_not_stale(doc, modified)
    if doc.get("status") == "Cancelled":
        frappe.throw(_("Cancelled Hospitalisation charges are read-only."), frappe.ValidationError)

    row = next((item for item in doc.get("charge_items") or [] if item.get("name") == charge_row_name), None)
    if not row:
        frappe.throw(_("Hospitalisation charge item could not be found."), frappe.DoesNotExistError)

    editable, editable_fields, reason = _charge_editability(doc, row)
    if not editable:
        frappe.throw(reason or _("This Hospitalisation charge is read-only."), frappe.ValidationError)

    payload = _parse_payload(values)
    payload = {key: value for key, value in payload.items() if key in CHARGE_EDIT_FIELDS and key in editable_fields}
    if not payload:
        return {"charge": {}, "episode": get_hospitalisation_episode(hospitalisation_name)}

    original_keys = set(service.get_charge_item_identity_keys(row))
    item = _clean(payload.get("item")) if "item" in payload else _clean(row.get("item"))
    if not item:
        frappe.throw(_("ERPNext Item is required for a Hospitalisation charge."), frappe.ValidationError)
    validate_sales_item(item, "Hospitalisation Charge Item", allow_stock=True)

    qty = flt(payload.get("qty")) if "qty" in payload else flt(row.get("qty"))
    if qty <= 0:
        frappe.throw(_("Hospitalisation charge quantity must be greater than zero."), frappe.ValidationError)
    uom = _clean(payload.get("uom")) if "uom" in payload else _clean(row.get("uom"))
    if not uom:
        uom = frappe.db.get_value("Item", item, "stock_uom")

    if "rate" in payload:
        rate = flt(payload.get("rate"))
        if rate < 0:
            frappe.throw(_("Hospitalisation charge Rate cannot be negative."), frappe.ValidationError)
        pricing_source = "Manual"
    else:
        rate = flt(row.get("rate"))
        pricing_source = row.get("pricing_source")
        if "item" in payload and item != row.get("item"):
            pricing = service.resolve_hospitalisation_charge_pricing(doc, item, uom)
            rate = flt(pricing.get("rate"))
            pricing_source = pricing.get("pricing_source")

    row.item = item
    row.item_name = service.get_item_name(item)
    row.qty = qty
    row.uom = uom
    row.rate = rate
    row.amount = qty * rate
    row.pricing_source = pricing_source
    if "description" in payload:
        row.description = payload.get("description")

    for activity in doc.get("activities") or []:
        activity_keys = set(service.get_activity_charge_lookup_keys(doc.name, activity))
        if not original_keys.intersection(activity_keys):
            continue
        if "item" in payload:
            activity.item = item
        if "qty" in payload:
            activity.qty = qty
        if "uom" in payload:
            activity.uom = uom
        if not is_hospitalisation_dispensary_enabled() and not activity.get("stock_entry"):
            activity.stock_affecting = 0
            activity.stock_status = "Not Applicable"
        break

    doc.save()
    invoice = _invoice_state(row.get("sales_invoice"))
    return {
        "charge": {
            "name": row.get("name"),
            "item": row.get("item"),
            "qty": flt(row.get("qty")),
            "uom": row.get("uom"),
            "rate": flt(row.get("rate")),
            "amount": flt(row.get("amount")),
        },
        "invoice_sync_required": bool(invoice and cint(invoice.get("docstatus")) == 0),
        "message": _("Hospitalisation charge updated. Sync Charges to Invoice to refresh any linked draft invoice."),
        "episode": get_hospitalisation_episode(hospitalisation_name),
    }


@frappe.whitelist()
def get_hospitalisation_stock_posting_preview(hospitalisation_name: str, activity_row_name: str | None = None) -> dict:
    if not is_hospitalisation_dispensary_enabled():
        return {
            "hospitalisation": hospitalisation_name,
            "to_post_count": 0,
            "skipped_count": 0,
            "blocked_count": 0,
            "shortage_count": 0,
            "items": [],
            "skipped": [],
            "blocked": [],
            "warnings": [_('Dispensary Flow is disabled in Veterinary Settings.')],
            "can_post": False,
            "disabled": True,
        }
    from vetedge.services.hospitalisation import get_hospitalisation_stock_posting_preview as original

    return original(hospitalisation_name, activity_row_name)


@frappe.whitelist()
def post_hospitalisation_activity_stock(hospitalisation_name: str, activity_row_name: str | None = None) -> dict:
    if not is_hospitalisation_dispensary_enabled():
        frappe.throw(_("Dispensary Flow is disabled in Veterinary Settings; Hospitalisation stock posting is unavailable."), frappe.ValidationError)
    from vetedge.services.hospitalisation import post_hospitalisation_activity_stock as original

    return original(hospitalisation_name, activity_row_name)


@frappe.whitelist()
def generate_hospitalisation_daily_charges(
    hospitalisation_name: str,
    from_date=None,
    to_date=None,
    care_level: str | None = None,
) -> dict:
    if not is_hospitalisation_daily_charges_enabled():
        return _daily_charge_disabled_result(hospitalisation_name)
    from vetedge.services.hospitalisation import generate_hospitalisation_daily_charges as original

    return original(hospitalisation_name, from_date=from_date, to_date=to_date, care_level=care_level)


@frappe.whitelist()
def admit_hospitalisation(hospitalisation_name: str) -> dict:
    if not is_hospitalisation_daily_charges_enabled():
        settings = frappe.get_single(SETTINGS_DOCTYPE) if frappe.db.exists("DocType", SETTINGS_DOCTYPE) else None
        if settings and settings.get("hospitalisation_initial_billing_source") == "Day 1 Daily Charge":
            return {
                "allowed": False,
                "blocked": True,
                "can_proceed": False,
                "status": "Blocked",
                "message": _(
                    "Hospitalisation Initial Billing Source is Day 1 Daily Charge, but Hospitalisation Daily Charges are disabled. Change the initial billing source or enable daily charges."
                ),
                "reload_required": True,
                "hospitalisation": hospitalisation_name,
            }
    from vetedge.services.hospitalisation import admit_hospitalisation as original

    return original(hospitalisation_name)


@frappe.whitelist()
def get_hospitalisation_discharge_readiness(hospitalisation_name: str) -> dict:
    doc = _load_hospitalisation(hospitalisation_name, write=not is_hospitalisation_dispensary_enabled())
    if not is_hospitalisation_dispensary_enabled():
        _normalize_unposted_stock_flags_when_dispensary_disabled(doc)
    from vetedge.services.hospitalisation import get_hospitalisation_discharge_readiness as original

    return original(hospitalisation_name)


@frappe.whitelist()
def discharge_hospitalisation(
    hospitalisation_name: str,
    discharge_summary: str | None = None,
    force: bool = False,
    discharge_details=None,
) -> dict:
    doc = _load_hospitalisation(hospitalisation_name, write=True)
    if not is_hospitalisation_dispensary_enabled():
        _normalize_unposted_stock_flags_when_dispensary_disabled(doc)
    from vetedge.services.hospitalisation import discharge_hospitalisation as original

    return original(
        hospitalisation_name,
        discharge_summary=discharge_summary,
        force=force,
        discharge_details=discharge_details,
    )


@frappe.whitelist()
def perform_hospitalisation_episode_action(
    name: str,
    action: str,
    values=None,
    modified: str | None = None,
) -> dict[str, Any]:
    action = _clean(action)
    values = _parse_payload(values)
    doc = _load_hospitalisation(name, write=action not in {"stock_preview", "check_discharge_readiness"})
    if action not in {"stock_preview", "check_discharge_readiness"}:
        _assert_not_stale(doc, modified)

    if action == "stock_preview":
        result = get_hospitalisation_stock_posting_preview(name, values.get("activity_row_name"))
        return {"result": result, "episode": get_hospitalisation_episode(name)}
    if action == "post_stock":
        result = post_hospitalisation_activity_stock(name, values.get("activity_row_name"))
        return {"result": result, "episode": get_hospitalisation_episode(name)}
    if action == "generate_daily_charges":
        result = generate_hospitalisation_daily_charges(
            name,
            from_date=values.get("from_date"),
            to_date=values.get("to_date"),
            care_level=values.get("care_level") or doc.get("care_level"),
        )
        return {"result": result, "episode": get_hospitalisation_episode(name)}
    if action == "admit":
        result = admit_hospitalisation(name)
        return {"result": result, "episode": get_hospitalisation_episode(name)}
    if action == "check_discharge_readiness":
        result = get_hospitalisation_discharge_readiness(name)
        return {"result": result, "episode": get_hospitalisation_episode(name)}
    if action == "discharge":
        result = discharge_hospitalisation(
            name,
            discharge_details=values.get("discharge_details") or values,
            force=False,
        )
        return {"result": result, "episode": get_hospitalisation_episode(name)}

    from vetedge.services.hospitalisation_episode import perform_hospitalisation_episode_action as original

    result = original(name=name, action=action, values=values, modified=modified)
    result["episode"] = _enrich_episode(result.get("episode"))
    return result
