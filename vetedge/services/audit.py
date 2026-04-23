from __future__ import annotations

import json
import logging

import frappe


def log_operational_event(
	action: str,
	outcome: str,
	user: str | None = None,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	details: dict | None = None,
) -> None:
	payload = {
		"action": action,
		"outcome": outcome,
		"user": user or get_current_user(),
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
		"details": details or {},
	}
	message = json.dumps(payload, default=str, sort_keys=True)
	logger = _get_audit_logger()
	if outcome == "blocked":
		logger.warning(message)
	else:
		logger.info(message)


def get_current_user() -> str | None:
	try:
		return getattr(frappe.session, "user", None)
	except RuntimeError:
		return None


def _get_audit_logger():
	try:
		return frappe.logger("vetedge.audit")
	except Exception:
		return logging.getLogger("vetedge.audit")
