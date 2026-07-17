from __future__ import annotations

from importlib import import_module

import frappe


def send_sms_safe(**kwargs) -> dict:
	try:
		send_sms = import_module("coreedge.coreedge.sms_engine").send_sms
	except ImportError:
		return {"ok": False, "status": "CoreEdge Unavailable", "reason_code": "COREDGE_NOT_INSTALLED"}

	try:
		return send_sms(**kwargs)
	except Exception as exc:
		if getattr(frappe, "log_error", None):
			frappe.log_error(title="VetEdge Safe SMS Call Failed", message=frappe.get_traceback())
		return {"ok": False, "status": "Failed", "reason_code": "COREDGE_SMS_ERROR", "message": str(exc)}
