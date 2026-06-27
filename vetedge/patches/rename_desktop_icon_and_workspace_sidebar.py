# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe


def execute() -> None:
	# 1. Revert Workspace Sidebar rename safely before sync
	if frappe.db.exists("DocType", "Workspace Sidebar"):
		if frappe.db.exists("Workspace Sidebar", "Veterinary") and not frappe.db.exists("Workspace Sidebar", "VetEdge"):
			frappe.rename_doc("Workspace Sidebar", "Veterinary", "VetEdge", force=True)

		if frappe.db.exists("Workspace Sidebar", "Veterinary") and frappe.db.exists("Workspace Sidebar", "VetEdge"):
			frappe.delete_doc("Workspace Sidebar", "Veterinary", force=True)

	# 2. Revert Desktop Icon rename safely before sync
	if frappe.db.exists("DocType", "Desktop Icon"):
		if frappe.db.exists("Desktop Icon", "Veterinary") and not frappe.db.exists("Desktop Icon", "VetEdge"):
			frappe.rename_doc("Desktop Icon", "Veterinary", "VetEdge", force=True)

		if frappe.db.exists("Desktop Icon", "Veterinary") and frappe.db.exists("Desktop Icon", "VetEdge"):
			frappe.delete_doc("Desktop Icon", "Veterinary", force=True)

	# 3. Normalize Website Settings safely
	if frappe.db.exists("DocType", "Website Settings"):
		try:
			web_settings = frappe.get_doc("Website Settings", "Website Settings")
			changed = False
			if web_settings.app_name == "VetEdge":
				web_settings.app_name = "Veterinary"
				changed = True
			if web_settings.footer_powered == "VetEdge":
				web_settings.footer_powered = "Veterinary"
				changed = True
			if changed:
				web_settings.save(ignore_permissions=True)
		except Exception:
			pass
