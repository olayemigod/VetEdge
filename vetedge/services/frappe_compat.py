from __future__ import annotations

import frappe
from frappe.model.meta import Meta
from frappe.model.workflow import get_workflow_name


def get_meta_workflow_state_field(meta: Meta) -> str:
	"""Resolve an active Workflow state field without assuming Meta exposes it.

	Frappe 16.27.0 keeps ``workflow_state_field`` on the active Workflow
	document, while newer version-16 builds may expose a convenience attribute
	on Meta. Keep VetEdge compatible with both forms.
	"""
	workflow_name = get_workflow_name(meta.name)
	if not workflow_name:
		return ""

	fieldname = frappe.get_cached_value("Workflow", workflow_name, "workflow_state_field") or ""
	if fieldname and meta.has_field(fieldname):
		return str(fieldname)
	return ""


def install_meta_workflow_state_field_compat() -> None:
	"""Install the missing Meta compatibility property on older Frappe v16."""
	if hasattr(Meta, "workflow_state_field"):
		return

	Meta.workflow_state_field = property(get_meta_workflow_state_field)  # type: ignore[attr-defined]
