# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
import frappe


class TestDocTypeRename(unittest.TestCase):
	def test_new_doctypes_exist(self) -> None:
		new_doctypes = [
			"Veterinary License Profile",
			"Veterinary Notification Log",
			"Veterinary Notification Preference",
			"Veterinary Role Bundle",
			"Veterinary Role Bundle Role",
		]
		for dt in new_doctypes:
			self.assertTrue(
				frappe.db.exists("DocType", dt),
				f"Expected DocType {dt} to exist, but it was not found."
			)

	def test_old_doctypes_do_not_exist(self) -> None:
		old_doctypes = [
			"VetEdge License Profile",
			"VetEdge Notification Log",
			"VetEdge Notification Preference",
			"VetEdge Role Bundle",
			"VetEdge Role Bundle Role",
		]
		for dt in old_doctypes:
			self.assertFalse(
				frappe.db.exists("DocType", dt),
				f"Old DocType {dt} should not exist, but it was found."
			)

	def test_role_bundle_child_table_option(self) -> None:
		meta = frappe.get_meta("Veterinary Role Bundle")
		roles_field = meta.get_field("roles")
		self.assertIsNotNone(roles_field, "Field 'roles' not found in Veterinary Role Bundle")
		self.assertEqual(
			roles_field.options,
			"Veterinary Role Bundle Role",
			f"Expected child table options to point to 'Veterinary Role Bundle Role', but got '{roles_field.options}'"
		)

	def test_new_report_exists(self) -> None:
		self.assertTrue(
			frappe.db.exists("Report", "Veterinary Notification Event Registry"),
			"Expected Report 'Veterinary Notification Event Registry' to exist, but it was not found."
		)

	def test_old_report_does_not_exist(self) -> None:
		self.assertFalse(
			frappe.db.exists("Report", "VetEdge Notification Event Registry"),
			"Old Report 'VetEdge Notification Event Registry' should not exist, but it was found."
		)
