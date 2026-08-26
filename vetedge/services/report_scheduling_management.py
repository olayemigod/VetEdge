from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr

from vetedge.services.portal_access import require_internal_user
from vetedge.services.report_scheduling import AUTO_EMAIL_DOCTYPE, BRIDGE_REPORT, DESCRIPTION_PREFIX
from vetedge.services.report_scheduling_compatibility import REPORT_CATALOG, canonical_report_name


def _target_report(row: dict) -> str:
	description = cstr(row.get("description") or "")
	if description.startswith(DESCRIPTION_PREFIX):
		return canonical_report_name(description[len(DESCRIPTION_PREFIX) :].strip())
	if row.get("report") == BRIDGE_REPORT:
		try:
			filters = json.loads(row.get("filters") or "{}")
			return canonical_report_name(filters.get("target_report") or "")
		except Exception:
			return ""
	return canonical_report_name(row.get("report") or "")


def _owned_schedule(name: str):
	doc = frappe.get_doc(AUTO_EMAIL_DOCTYPE, name)
	if doc.user != frappe.session.user:
		frappe.throw(_("You may manage only your own scheduled report deliveries."), frappe.PermissionError)
	target = _target_report(doc.as_dict())
	if target not in REPORT_CATALOG:
		frappe.throw(_("This is not a VetEdge report schedule."), frappe.PermissionError)
	return doc, target


@frappe.whitelist()
@frappe.read_only()
def get_my_report_schedules(report_name: str | None = None) -> list[dict]:
	require_internal_user()
	rows = frappe.get_list(
		AUTO_EMAIL_DOCTYPE,
		filters={"user": frappe.session.user},
		fields=[
			"name",
			"report",
			"description",
			"filters",
			"email_to",
			"frequency",
			"day_of_week",
			"format",
			"enabled",
			"send_if_data",
			"no_of_rows",
			"modified",
		],
		order_by="modified desc",
		page_length=100,
	)
	requested = canonical_report_name(report_name or "") if report_name else ""
	items = []
	for row in rows:
		target = _target_report(row)
		if target not in REPORT_CATALOG or (requested and target != requested):
			continue
		items.append(
			{
				"name": row.get("name"),
				"report_name": target,
				"delivery_mode": "vetedge_export_adapter" if row.get("report") == BRIDGE_REPORT else "native_auto_email",
				"email_to": row.get("email_to"),
				"frequency": row.get("frequency"),
				"day_of_week": row.get("day_of_week"),
				"format": row.get("format"),
				"enabled": bool(cint(row.get("enabled"))),
				"send_if_data": bool(cint(row.get("send_if_data"))),
				"no_of_rows": cint(row.get("no_of_rows")),
				"modified": row.get("modified"),
			}
		)
	return items


@frappe.whitelist()
def set_report_schedule_enabled(name: str, enabled: int) -> dict:
	require_internal_user()
	doc, target = _owned_schedule(name)
	doc.check_permission("write")
	doc.enabled = cint(enabled)
	doc.save()
	return {"name": doc.name, "report_name": target, "enabled": bool(cint(doc.enabled))}


@frappe.whitelist()
def delete_report_schedule(name: str) -> dict:
	require_internal_user()
	doc, target = _owned_schedule(name)
	doc.check_permission("delete")
	doc.delete()
	return {"name": name, "report_name": target, "deleted": True}
