# -*- coding: utf-8 -*-
from __future__ import annotations

import frappe


def execute() -> None:
	# 1. Rename DocTypes
	doctypes_to_rename = [
		("VetEdge License Profile", "Veterinary License Profile"),
		("VetEdge Notification Log", "Veterinary Notification Log"),
		("VetEdge Notification Preference", "Veterinary Notification Preference"),
		("VetEdge Role Bundle", "Veterinary Role Bundle"),
		("VetEdge Role Bundle Role", "Veterinary Role Bundle Role"),
	]
	for old_dt, new_dt in doctypes_to_rename:
		if frappe.db.exists("DocType", old_dt) and not frappe.db.exists("DocType", new_dt):
			frappe.rename_doc("DocType", old_dt, new_dt, force=True)

	# 2. Rename Reports
	reports_to_rename = [
		("VetEdge Notification Event Registry", "Veterinary Notification Event Registry")
	]
	for old_rep, new_rep in reports_to_rename:
		if frappe.db.exists("Report", old_rep) and not frappe.db.exists("Report", new_rep):
			frappe.rename_doc("Report", old_rep, new_rep, force=True)
