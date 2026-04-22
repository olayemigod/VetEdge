from __future__ import annotations

import frappe

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
	context.dashboard = get_owner_portal_dashboard()
	return context
