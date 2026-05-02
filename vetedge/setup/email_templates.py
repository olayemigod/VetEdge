from __future__ import annotations

import json
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = APP_ROOT / "fixtures" / "vetedge_email_templates.json"
MANAGED_MARKER_PREFIX = "<!-- vetedge-managed-email-template:"

SYNCABLE_FIELDS = (
	"enabled",
	"use_html",
	"subject",
	"reference_doctype",
)


def sync_vetedge_email_templates(force: bool | None = None) -> dict[str, list[str]]:
	import frappe

	force = _coerce_force_flag(force)
	summary = {"created": [], "updated": [], "skipped": []}

	if not FIXTURE_PATH.exists():
		summary["skipped"].append(f"Fixture missing: {FIXTURE_PATH}")
		_log_sync_summary(summary, force=force)
		return summary

	for template_row in _load_fixture_templates():
		result, reason = _sync_email_template(template_row, force=force)
		summary[result].append(f"{template_row['name']} ({reason})")

	_log_sync_summary(summary, force=force)
	return summary


def _load_fixture_templates() -> list[dict]:
	rows = json.loads(FIXTURE_PATH.read_text())
	return [row for row in rows if row.get("doctype") == "Email Template" and row.get("name")]


def _sync_email_template(template_row: dict, force: bool) -> tuple[str, str]:
	import frappe

	template_name = template_row["name"]
	doc_payload = _build_template_payload(template_row)

	if not frappe.db.exists("Email Template", template_name):
		frappe.get_doc(doc_payload).insert(ignore_permissions=True)
		return "created", "created from fixture"

	doc = frappe.get_doc("Email Template", template_name)
	if not _can_update_existing_template(doc, template_row, force=force):
		return "skipped", "existing template appears client-edited"

	changed = _apply_template_payload(doc, doc_payload)
	if not changed:
		return "skipped", "already in sync"

	doc.save(ignore_permissions=True)
	return "updated", "updated from fixture"


def _build_template_payload(template_row: dict) -> dict:
	payload = {
		"doctype": "Email Template",
		"name": template_row["name"],
	}

	for fieldname in SYNCABLE_FIELDS:
		if fieldname not in template_row:
			continue
		payload[fieldname] = template_row[fieldname]

	response = _ensure_managed_marker(template_row.get("response") or "", template_row["name"])
	if template_row.get("use_html"):
		payload["response_html"] = response
		payload["response"] = ""
	else:
		payload["response"] = response
		payload["response_html"] = ""

	return payload


def _apply_template_payload(doc, payload: dict) -> bool:
	changed = False

	for fieldname in (*SYNCABLE_FIELDS, "response", "response_html"):
		if fieldname not in payload:
			continue

		if doc.get(fieldname) == payload[fieldname]:
			continue

		doc.set(fieldname, payload[fieldname])
		changed = True

	return changed


def _can_update_existing_template(doc, template_row: dict, force: bool) -> bool:
	if force:
		return True

	if _is_managed_template(doc):
		return True

	return _matches_fixture(doc, template_row)


def _matches_fixture(doc, template_row: dict) -> bool:
	fixture_response = _strip_managed_marker(template_row.get("response") or "")
	current_response = _strip_managed_marker(_get_current_template_response(doc))

	return (
		doc.get("subject") == (template_row.get("subject") or "")
		and current_response == fixture_response
		and (doc.get("enabled") or 0) == (template_row.get("enabled") or 0)
		and (doc.get("use_html") or 0) == (template_row.get("use_html") or 0)
		and (doc.get("reference_doctype") or "") == (template_row.get("reference_doctype") or "")
	)


def _is_managed_template(doc) -> bool:
	return _get_current_template_response(doc).lstrip().startswith(MANAGED_MARKER_PREFIX)


def _get_current_template_response(doc) -> str:
	if doc.get("use_html"):
		return doc.get("response_html") or doc.get("response") or ""
	return doc.get("response") or doc.get("response_html") or ""


def _ensure_managed_marker(response: str, template_name: str) -> str:
	response = response or ""
	if response.lstrip().startswith(MANAGED_MARKER_PREFIX):
		return response
	return f"{MANAGED_MARKER_PREFIX}{template_name} -->\n{response}"


def _strip_managed_marker(response: str) -> str:
	response = response or ""
	stripped = response.lstrip()
	if not stripped.startswith(MANAGED_MARKER_PREFIX):
		return response

	marker_end = stripped.find("-->")
	if marker_end == -1:
		return response

	return stripped[marker_end + 3 :].lstrip("\n")


def _coerce_force_flag(force: bool | None) -> bool:
	import frappe

	if force is not None:
		return bool(force)

	return bool(getattr(frappe.flags, "force_vetedge_email_template_sync", False))


def _log_sync_summary(summary: dict[str, list[str]], force: bool) -> None:
	import frappe

	message = (
		"VetEdge Email Template sync complete "
		f"(force={int(force)}): "
		f"{len(summary['created'])} created, "
		f"{len(summary['updated'])} updated, "
		f"{len(summary['skipped'])} skipped"
	)
	frappe.logger("vetedge.email_templates").info(message)
