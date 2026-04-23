from __future__ import annotations

import frappe
from frappe.utils import cint

from vetedge.services.owner_portal import get_owner_portal_dashboard
from vetedge.services.portal_access import get_portal_settings


no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/vetedge_portal"
		raise frappe.Redirect

	portal_theme = get_portal_settings().get("portal_theme", {})
	brand_name = portal_theme.get("brand_name") or "Owner"
	context.title = f"{brand_name} Owner Portal"
	context.owner_portal_page = "overview"
	context.portal_subtitle = "A quick view of pets, appointments, billing, and clinical summaries."
	context.dashboard = get_owner_portal_dashboard(build_page_context())
	return context


def build_page_context() -> dict:
	request = getattr(frappe, "request", None)
	form_dict = getattr(frappe, "form_dict", frappe._dict()) or frappe._dict()
	return {
		"current_path": getattr(request, "path", None) or "/vetedge_portal",
		"appointment_history_page": max(cint(form_dict.get("history_page")) or 1, 1),
		"outstanding_invoice_page": max(cint(form_dict.get("outstanding_page")) or 1, 1),
		"paid_invoice_page": max(cint(form_dict.get("paid_page")) or 1, 1),
		"consultation_page": max(cint(form_dict.get("consultation_page")) or 1, 1),
	}
