from __future__ import annotations

import frappe

from vetedge.coreedge_adapter import has_vetedge_access


def get_product_availability() -> dict | None:
	"""Return Veterinary only when it is available to the current Desk user."""
	user = frappe.session.user
	if not user or user == "Guest":
		return None
	if user != "Administrator" and frappe.db.get_value("User", user, "user_type") != "System User":
		return None
	if not has_vetedge_access(user=user):
		return None
	return {
		"key": "vetedge",
		"label": "Veterinary",
		"product": "Veterinary",
		"icon": "stethoscope",
		"home_route": "/app/vetedge",
		"route_patterns": [
			"/app/vetedge*",
			"/app/veterinary-*",
			"/app/stock-expiry-monitor*",
			"/app/query-report/Veterinary*",
		],
		"order": 30,
	}
