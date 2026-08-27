from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, now, now_datetime

from vetedge.services import hospitalisation_episode_policy as base_policy


HOSPITALISATION_DOCTYPE = "Veterinary Hospitalisation"
SETTINGS_DOCTYPE = "Veterinary Settings"
VACCINATION_DOCTYPE = "Veterinary Vaccination Record"
LAB_ORDER_DOCTYPE = "Veterinary Lab Order"


def _clean(value: Any) -> str:
    return cstr(value or "").strip()


def _require_hospitalisation_access(
    hospitalisation_name: str,
    *,
    write: bool = False,
    platform_action: str | None = None,
):
    """Apply the normal Hospitalisation security boundary before policy shortcuts.

    Feature-disabled responses must never be an easier API path than the enabled
    core service. The policy layer therefore resolves internal-user, feature,
    document permission, branch and (where the original service uses it)
    platform access before returning a disabled/blocked response.
    """
    from vetedge.services.hospitalisation import assert_hospitalisation_enabled

    assert_hospitalisation_enabled()
    doc = base_policy._load_hospitalisation(hospitalisation_name, write=write)
    if platform_action:
        from vetedge.services.platform_access import require_vetedge_platform_access

        require_vetedge_platform_access(
            action=platform_action,
            reference_doctype=HOSPITALISATION_DOCTYPE,
            reference_name=hospitalisation_name,
        )
    return doc


def _episode_module():
    from vetedge.services import hospitalisation_episode

    return hospitalisation_episode


def _append_linked_timeline_activity(
    doc,
    *,
    activity_type: str,
    clinical_notes: str | None,
    linked_doctype: str,
    linked_document: str,
    item: str | None = None,
    qty: float | None = None,
    activity_datetime=None,
):
    """Append an operational timeline row without creating parallel billing/stock truth."""
    episode = _episode_module()
    episode._assert_open_episode(doc)
    row = episode._append_activity(
        doc,
        {
            "activity_type": activity_type,
            "activity_datetime": activity_datetime or now_datetime(),
            "clinical_notes": clinical_notes,
            "billable": 0,
            "stock_affecting": 0,
            "item": item,
            "qty": qty,
            "linked_doctype": linked_doctype,
            "linked_document": linked_document,
        },
    )
    doc.save()
    return row


def _create_hospitalisation_vaccination_record(doc, values: dict[str, Any]) -> str:
    if doc.get("linked_consultation"):
        from vetedge.services.vaccination import create_vaccination_from_consultation

        result = create_vaccination_from_consultation(
            consultation=doc.get("linked_consultation"),
            values=values,
            create_invoice=0,
            post_stock=0,
        )
        name = result.get("name") if isinstance(result, dict) else None
    else:
        name = base_policy._create_direct_hospitalisation_vaccination(doc, values)

    if not name:
        frappe.throw(_("Vaccination Record could not be created."), frappe.ValidationError)
    base_policy._link_record_to_hospitalisation(VACCINATION_DOCTYPE, name, doc.name)
    return name


@frappe.whitelist()
def add_hospitalisation_vaccination(
    hospitalisation_name: str,
    values=None,
    modified: str | None = None,
) -> dict[str, Any]:
    """Create one authoritative Vaccination Record and a timeline-only Hospitalisation row.

    Vaccination owns its payment gate, billing and stock administration. The
    Hospitalisation activity intentionally does not duplicate those authorities.
    """
    doc = _require_hospitalisation_access(hospitalisation_name, write=True)
    base_policy._assert_not_stale(doc, modified)
    episode = _episode_module()
    episode._assert_open_episode(doc)
    payload = base_policy._parse_payload(values)
    vaccine = _clean(payload.get("vaccine"))
    if not vaccine:
        frappe.throw(_("Vaccine is required."), frappe.ValidationError)

    linked_record = _create_hospitalisation_vaccination_record(doc, payload)
    vaccine_row = frappe.db.get_value(
        "Veterinary Vaccine",
        vaccine,
        ["vaccine_name", "default_item"],
        as_dict=True,
    ) or {}
    notes = episode._format_notes(
        [
            (_("Vaccine"), vaccine_row.get("vaccine_name") or vaccine),
            (_("Dose"), payload.get("dose")),
            (_("Route"), payload.get("route")),
            (_("Next Due"), payload.get("next_due_date")),
        ],
        payload.get("notes"),
    )
    row = _append_linked_timeline_activity(
        doc,
        activity_type="Vaccination",
        clinical_notes=notes,
        linked_doctype=VACCINATION_DOCTYPE,
        linked_document=linked_record,
        item=vaccine_row.get("default_item"),
        qty=1 if vaccine_row.get("default_item") else None,
        activity_datetime=payload.get("administered_on") or now_datetime(),
    )
    warning = _(
        "Vaccination billing, payment and stock administration are controlled by the linked Vaccination Record. "
        "The Hospitalisation row is a clinical timeline reference only."
    )
    return {
        "activity": episode._activity_payload(row),
        "linked_record": linked_record,
        "warning": warning,
        "episode": base_policy.get_hospitalisation_episode(hospitalisation_name),
    }


def _create_hospitalisation_lab_order(doc, lab_tests, sample_notes: str | None) -> str:
    if doc.get("linked_consultation"):
        from vetedge.services.lab import create_lab_order_from_consultation

        result = create_lab_order_from_consultation(
            consultation=doc.get("linked_consultation"),
            lab_tests=lab_tests,
            sample_notes=sample_notes,
        )
        name = result.get("name") if isinstance(result, dict) else None
    else:
        name = base_policy._create_direct_hospitalisation_lab_order(doc, lab_tests, sample_notes)

    if not name:
        frappe.throw(_("Lab Order could not be created."), frappe.ValidationError)
    base_policy._link_record_to_hospitalisation(LAB_ORDER_DOCTYPE, name, doc.name)
    return name


@frappe.whitelist()
def add_hospitalisation_lab_order(
    hospitalisation_name: str,
    lab_tests=None,
    sample_notes: str | None = None,
    modified: str | None = None,
) -> dict[str, Any]:
    """Create one authoritative Lab Order and timeline-only Hospitalisation rows."""
    doc = _require_hospitalisation_access(hospitalisation_name, write=True)
    base_policy._assert_not_stale(doc, modified)
    episode = _episode_module()
    episode._assert_open_episode(doc)

    linked_order = _create_hospitalisation_lab_order(doc, lab_tests, sample_notes)
    order = frappe.get_doc(LAB_ORDER_DOCTYPE, linked_order)
    created = []
    for test in order.get("lab_tests") or []:
        label = test.get("lab_test_name") or test.get("lab_test_template") or _("Lab Test")
        notes = "\n".join(filter(None, [cstr(label), _clean(sample_notes)]))
        created.append(
            _append_linked_timeline_activity(
                doc,
                activity_type="Lab",
                clinical_notes=notes,
                linked_doctype=LAB_ORDER_DOCTYPE,
                linked_document=linked_order,
                item=test.get("billing_item"),
                qty=1 if test.get("billing_item") else None,
            )
        )

    return {
        "linked_order": linked_order,
        "created_count": len(created),
        "warning": _(
            "Lab billing and payment are controlled by the linked Lab Order. "
            "Hospitalisation Lab rows are clinical timeline references only."
        ),
        "episode": base_policy.get_hospitalisation_episode(hospitalisation_name),
    }


def _disabled_stock_preview(hospitalisation_name: str) -> dict[str, Any]:
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


@frappe.whitelist()
def get_hospitalisation_stock_posting_preview(
    hospitalisation_name: str,
    activity_row_name: str | None = None,
) -> dict:
    _require_hospitalisation_access(hospitalisation_name)
    if not base_policy.is_hospitalisation_dispensary_enabled():
        return _disabled_stock_preview(hospitalisation_name)
    from vetedge.services.hospitalisation import get_hospitalisation_stock_posting_preview as original

    return original(hospitalisation_name, activity_row_name)


@frappe.whitelist()
def post_hospitalisation_activity_stock(
    hospitalisation_name: str,
    activity_row_name: str | None = None,
) -> dict:
    _require_hospitalisation_access(hospitalisation_name, write=True)
    if not base_policy.is_hospitalisation_dispensary_enabled():
        frappe.throw(
            _("Dispensary Flow is disabled in Veterinary Settings; Hospitalisation stock posting is unavailable."),
            frappe.ValidationError,
        )
    from vetedge.services.hospitalisation import post_hospitalisation_activity_stock as original

    return original(hospitalisation_name, activity_row_name)


@frappe.whitelist()
def generate_hospitalisation_daily_charges(
    hospitalisation_name: str,
    from_date=None,
    to_date=None,
    care_level: str | None = None,
) -> dict:
    _require_hospitalisation_access(hospitalisation_name, write=True)
    if not base_policy.is_hospitalisation_daily_charges_enabled():
        return base_policy._daily_charge_disabled_result(hospitalisation_name)
    from vetedge.services.hospitalisation import generate_hospitalisation_daily_charges as original

    return original(hospitalisation_name, from_date=from_date, to_date=to_date, care_level=care_level)


@frappe.whitelist()
def admit_hospitalisation(hospitalisation_name: str) -> dict:
    _require_hospitalisation_access(
        hospitalisation_name,
        write=True,
        platform_action="admit_hospitalisation",
    )
    if not base_policy.is_hospitalisation_daily_charges_enabled():
        settings = frappe.get_single(SETTINGS_DOCTYPE) if frappe.db.exists("DocType", SETTINGS_DOCTYPE) else None
        if settings and settings.get("hospitalisation_initial_billing_source") == "Day 1 Daily Charge":
            return {
                "allowed": False,
                "blocked": True,
                "can_proceed": False,
                "status": "Blocked",
                "message": _(
                    "Hospitalisation Initial Billing Source is Day 1 Daily Charge, but Hospitalisation Daily Charges "
                    "are disabled. Change the initial billing source or enable daily charges."
                ),
                "reload_required": True,
                "hospitalisation": hospitalisation_name,
            }
    from vetedge.services.hospitalisation import admit_hospitalisation as original

    return original(hospitalisation_name)


def _readiness_without_disabled_stock(doc, readiness: dict, discharge_summary: str | None = None) -> dict:
    if base_policy.is_hospitalisation_dispensary_enabled():
        return readiness

    result = dict(readiness or {})
    stock_message = "There are stock-affecting activities that have not been posted."
    result["pending_stock_activities"] = []
    result["messages"] = [message for message in result.get("messages") or [] if message != stock_message]
    result["warnings"] = [message for message in result.get("warnings") or [] if message != stock_message]
    result["recommended_actions"] = [
        action for action in result.get("recommended_actions") or [] if action != "Post Stock Usage"
    ]
    has_summary = bool(discharge_summary or doc.get("discharge_summary"))
    result["can_discharge"] = bool(
        has_summary
        and not result.get("pending_billable_activities")
        and not result.get("pending_charge_items")
        and (result.get("payment_gate") or {}).get("can_proceed")
    )
    return result


@frappe.whitelist()
def get_hospitalisation_discharge_readiness(hospitalisation_name: str) -> dict:
    doc = _require_hospitalisation_access(hospitalisation_name)
    from vetedge.services import hospitalisation as service

    readiness = service.build_hospitalisation_discharge_readiness(doc)
    return _readiness_without_disabled_stock(doc, readiness)


@frappe.whitelist()
def discharge_hospitalisation(
    hospitalisation_name: str,
    discharge_summary: str | None = None,
    force: bool = False,
    discharge_details=None,
) -> dict:
    """Discharge without rewriting historical stock rows when Dispensary Flow is off."""
    doc = _require_hospitalisation_access(
        hospitalisation_name,
        write=True,
        platform_action="discharge_hospitalisation",
    )
    from vetedge.services import hospitalisation as service

    if doc.get("status") == "Cancelled":
        frappe.throw(_("Cancelled hospitalisations cannot be discharged."), frappe.ValidationError)
    if doc.get("status") == "Discharged":
        frappe.throw(_("Hospitalisation is already discharged."), frappe.ValidationError)
    if doc.get("status") not in service.DISCHARGE_ALLOWED_STATUSES:
        frappe.throw(_("Only admitted hospitalisations can be discharged."), frappe.ValidationError)

    details = service.normalize_discharge_details(discharge_summary, discharge_details)
    summary = details.get("discharge_summary") or doc.get("discharge_summary")
    if not summary:
        frappe.throw(_("Discharge summary is required before discharge."), frappe.ValidationError)

    readiness = service.build_hospitalisation_discharge_readiness(doc, discharge_summary=summary)
    readiness = _readiness_without_disabled_stock(doc, readiness, discharge_summary=summary)
    if readiness.get("pending_stock_activities"):
        return {
            "blocked": True,
            "reload_required": True,
            "reason": "pending_stock_posting",
            "message": _("Stock usage must be posted before discharge. Use Stock → Post Stock Usage."),
            "open_stock_action": True,
            "hospitalisation": doc.name,
            "status": doc.get("status"),
            "readiness": readiness,
        }
    if not readiness.get("can_discharge") and not cint(force):
        doc.discharge_billing_status = readiness.get("discharge_billing_status")
        doc.discharge_message = " ".join(readiness.get("messages") or [])[:1000]
        doc.save()
        frappe.throw(
            doc.discharge_message or _("Hospitalisation is not ready for discharge."),
            frappe.ValidationError,
        )

    doc.status = "Discharged"
    doc.discharged_by = frappe.session.user
    doc.discharge_datetime = now()
    doc.discharge_summary = summary
    for fieldname in ("condition_at_discharge", "discharge_instructions", "follow_up_date", "follow_up_notes"):
        if fieldname in details:
            doc.set(fieldname, details.get(fieldname))
    doc.discharge_billing_status = (
        "Override" if cint(force) and not readiness.get("can_discharge") else readiness.get("discharge_billing_status")
    )
    doc.discharge_message = " ".join(readiness.get("messages") or [])[:1000]
    doc.save()
    return {
        "hospitalisation": doc.name,
        "status": doc.status,
        "discharge_billing_status": doc.get("discharge_billing_status"),
        "readiness": readiness,
    }


@frappe.whitelist()
def perform_hospitalisation_episode_action(
    name: str,
    action: str,
    values=None,
    modified: str | None = None,
) -> dict[str, Any]:
    action = _clean(action)
    values = base_policy._parse_payload(values)
    doc = _require_hospitalisation_access(
        name,
        write=action not in {"stock_preview", "check_discharge_readiness"},
    )
    if action not in {"stock_preview", "check_discharge_readiness"}:
        base_policy._assert_not_stale(doc, modified)

    if action == "stock_preview":
        result = get_hospitalisation_stock_posting_preview(name, values.get("activity_row_name"))
        return {"result": result, "episode": base_policy.get_hospitalisation_episode(name)}
    if action == "post_stock":
        result = post_hospitalisation_activity_stock(name, values.get("activity_row_name"))
        return {"result": result, "episode": base_policy.get_hospitalisation_episode(name)}
    if action == "generate_daily_charges":
        result = generate_hospitalisation_daily_charges(
            name,
            from_date=values.get("from_date"),
            to_date=values.get("to_date"),
            care_level=values.get("care_level") or doc.get("care_level"),
        )
        return {"result": result, "episode": base_policy.get_hospitalisation_episode(name)}
    if action == "admit":
        result = admit_hospitalisation(name)
        return {"result": result, "episode": base_policy.get_hospitalisation_episode(name)}
    if action == "check_discharge_readiness":
        result = get_hospitalisation_discharge_readiness(name)
        return {"result": result, "episode": base_policy.get_hospitalisation_episode(name)}
    if action == "discharge":
        result = discharge_hospitalisation(
            name,
            discharge_details=values.get("discharge_details") or values,
            force=False,
        )
        return {"result": result, "episode": base_policy.get_hospitalisation_episode(name)}

    return base_policy.perform_hospitalisation_episode_action(
        name=name,
        action=action,
        values=values,
        modified=modified,
    )
