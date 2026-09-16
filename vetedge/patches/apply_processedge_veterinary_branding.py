# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe

from vetedge.install.dashboard import ensure_vetedge_desktop_icon
from vetedge.services.branding import get_shell_branding


LEGACY_PRODUCT_NAMES = {"", "VetEdge", "Veterinary", "ProcessEdge Veterinary"}


def execute() -> None:
	"""Refresh visible product branding without changing technical VetEdge identity.

	The resolver is deployment-mode aware:
	- shared_hosted -> ProcessEdge Veterinary
	- white_label -> tenant branding, or generic Veterinary if none is configured
	- standalone -> ProcessEdge Veterinary unless an explicit hidden-source brand is active
	"""
	branding = get_shell_branding()
	target_title = branding.get("app_title") or branding.get("brand_name") or "Veterinary"

	# Desktop Icon is a standard database record and needs an explicit refresh on
	# already-installed sites; fixture changes alone do not update every deployment.
	try:
		ensure_vetedge_desktop_icon()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "ProcessEdge Veterinary branding: desktop icon")

	# Only replace blank/known historical product names. Never overwrite an
	# unrelated customer value that may have been deliberately configured.
	if frappe.db.exists("DocType", "Website Settings"):
		try:
			settings = frappe.get_doc("Website Settings", "Website Settings")
			changed = False
			if (settings.app_name or "") in LEGACY_PRODUCT_NAMES and settings.app_name != target_title:
				settings.app_name = target_title
				changed = True
			if (settings.footer_powered or "") in LEGACY_PRODUCT_NAMES and settings.footer_powered != target_title:
				settings.footer_powered = target_title
				changed = True
			if changed:
				settings.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ProcessEdge Veterinary branding: website settings")

	try:
		frappe.cache.delete_key("desktop_icons")
		frappe.cache.delete_key("bootinfo")
	except Exception:
		pass
