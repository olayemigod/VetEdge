from __future__ import annotations

from functools import wraps
from typing import Any

import frappe
import frappe.model.workflow as workflow_module
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


def _document_doctype(doc: Any) -> str:
	if hasattr(doc, "doctype"):
		return str(doc.doctype or "")
	if isinstance(doc, dict):
		return str(doc.get("doctype") or "")
	if isinstance(doc, str):
		try:
			parsed = frappe.parse_json(doc)
		except Exception:
			return ""
		if isinstance(parsed, dict):
			return str(parsed.get("doctype") or "")
	return ""


def install_workflow_transition_compat() -> None:
	"""Avoid Frappe's visible 'Workflow not found' message for plain DocTypes.

	Frappe's ``get_transitions`` calls ``get_workflow`` unconditionally for an
	existing document. That raises through ``frappe.throw`` when the DocType has
	no active Workflow, which leaves a popup message even when a product caller
	catches the exception. VetEdge checks first and returns no transitions for
	plain status-driven documents.
	"""
	current = workflow_module.get_transitions
	if getattr(current, "__vetedge_no_workflow_guard__", False):
		return

	@wraps(current)
	def guarded_get_transitions(doc, workflow=None, raise_exception: bool = False):
		doctype = _document_doctype(doc)
		if workflow is None and doctype and not get_workflow_name(doctype):
			return []
		return current(doc, workflow=workflow, raise_exception=raise_exception)

	guarded_get_transitions.__vetedge_no_workflow_guard__ = True
	workflow_module.get_transitions = guarded_get_transitions
