from __future__ import annotations

import frappe

from vetedge.services.owner_portal import get_owner_portal_dashboard


no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/vetedge_portal"
		raise frappe.Redirect

	context.title = "VetEdge Owner Portal"
	context.owner_portal_page = "overview"
	context.portal_subtitle = "A quick view of pets, appointments, billing, and clinical summaries."
	context.dashboard = get_owner_portal_dashboard()
	return context
