from __future__ import annotations

import frappe

from vetedge.coreedge_adapter import has_vetedge_access


PRODUCT_DESCRIPTOR = {
	"key": "vetedge",
	"product_key": "vetedge",
	"label": "Veterinary",
	"product": "Veterinary",
	"icon": "stethoscope",
	"home_route": "/desk/vetedge",
	"route_patterns": [
		"/desk/vetedge*",
		"/desk/veterinary-*",
		"/desk/stock-expiry-monitor*",
		"/desk/query-report/Veterinary*",
	],
	"order": 30,
}


def get_product_availability() -> dict | None:
	"""Expose Veterinary only when the current Desk user may actually use VetEdge."""
	user = frappe.session.user
	if not user or user == "Guest":
		return None
	if user != "Administrator" and frappe.db.get_value("User", user, "user_type") != "System User":
		return None
	if not has_vetedge_access(user=user):
		return None
	return dict(PRODUCT_DESCRIPTOR)
