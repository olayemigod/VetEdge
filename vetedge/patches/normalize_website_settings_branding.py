# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe


from vetedge.services.branding import get_branding


def execute() -> None:
	# Revert database records of standard app identity from Veterinary back to VetEdge
	if frappe.db.exists("DocType", "Workspace Sidebar"):
		if frappe.db.exists("Workspace Sidebar", "Veterinary") and not frappe.db.exists("Workspace Sidebar", "VetEdge"):
			frappe.rename_doc("Workspace Sidebar", "Veterinary", "VetEdge", force=True)
		if frappe.db.exists("Workspace Sidebar", "Veterinary") and frappe.db.exists("Workspace Sidebar", "VetEdge"):
			frappe.delete_doc("Workspace Sidebar", "Veterinary", force=True)

	if frappe.db.exists("DocType", "Desktop Icon"):
		if frappe.db.exists("Desktop Icon", "Veterinary") and not frappe.db.exists("Desktop Icon", "VetEdge"):
			frappe.rename_doc("Desktop Icon", "Veterinary", "VetEdge", force=True)
		if frappe.db.exists("Desktop Icon", "Veterinary") and frappe.db.exists("Desktop Icon", "VetEdge"):
			frappe.delete_doc("Desktop Icon", "Veterinary", force=True)

	# Check if branding is active through site_config or coreedge
	branding = get_branding()
	if branding.get("enabled"):
		return

	# 1. Normalize Website Settings branding
	if frappe.db.exists("DocType", "Website Settings"):
		try:
			web_settings = frappe.get_doc("Website Settings", "Website Settings")
			changed = False
			app_name = web_settings.app_name or ""
			footer = web_settings.footer_powered or ""

			target_app_title = branding.get("app_title") or "VetEdge"

			# Only normalize blank values or known defaults
			if app_name in ("", "VetEdge", "Veterinary"):
				if app_name != target_app_title:
					web_settings.app_name = target_app_title
					changed = True
			
			if footer in ("", "VetEdge", "Veterinary"):
				if footer != target_app_title:
					web_settings.footer_powered = target_app_title
					changed = True

			if changed:
				web_settings.save(ignore_permissions=True)
		except Exception:
			pass
