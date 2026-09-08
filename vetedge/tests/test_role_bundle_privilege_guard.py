from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import frappe

from vetedge.services.role_bundle_security import (
	can_assign_role_from_bundle,
	get_assignable_role_names,
	validate_assignable_roles,
)


ROOT = Path(__file__).resolve().parents[2]


class TestRoleBundlePrivilegeGuard(unittest.TestCase):
	def test_vetedge_administrator_cannot_delegate_system_manager(self):
		with patch(
			"vetedge.services.role_bundle_security.get_user_roles",
			return_value={"VetEdge Administrator"},
		):
			self.assertFalse(can_assign_role_from_bundle("System Manager", user="vetadmin@example.com"))
			self.assertTrue(can_assign_role_from_bundle("VetEdge Doctor", user="vetadmin@example.com"))
			self.assertTrue(can_assign_role_from_bundle("Accounts User", user="vetadmin@example.com"))
			with patch(
				"vetedge.services.role_bundle_security._",
				side_effect=lambda message: message,
			), patch(
				"vetedge.services.role_bundle_security.frappe.throw",
				side_effect=frappe.PermissionError,
			):
				with self.assertRaises(frappe.PermissionError):
					validate_assignable_roles(["VetEdge Doctor", "System Manager"], user="vetadmin@example.com")

	def test_system_manager_may_manage_any_existing_role_bundle_role(self):
		with patch(
			"vetedge.services.role_bundle_security.get_user_roles",
			return_value={"System Manager"},
		):
			self.assertIsNone(get_assignable_role_names("admin@example.com"))
			self.assertTrue(can_assign_role_from_bundle("System Manager", user="admin@example.com"))
			self.assertTrue(can_assign_role_from_bundle("Accounts Manager", user="admin@example.com"))

	def test_application_path_revalidates_bundle_for_acting_user(self):
		text = (ROOT / "vetedge/services/role_bundles.py").read_text(encoding="utf-8")
		self.assertIn("validate_role_bundle_document(bundle, user=acting_user)", text)
		self.assertLess(
			text.index("validate_role_bundle_document(bundle, user=acting_user)"),
			text.index('user_doc = frappe.get_doc("User", target_user)'),
		)

	def test_doctype_controller_uses_privilege_guard_on_native_save(self):
		text = (
			ROOT
			/ "vetedge/veterinary/doctype/veterinary_role_bundle/veterinary_role_bundle.py"
		).read_text(encoding="utf-8")
		self.assertIn("validate_role_bundle_document", text)
		self.assertNotIn("validate_role_bundle(self)", text)

	def test_edgesuite_role_search_has_bounded_safe_endpoint(self):
		text = (ROOT / "vetedge/services/role_bundle_security.py").read_text(encoding="utf-8")
		self.assertIn("search_assignable_role_options", text)
		self.assertIn("ROLE_BUNDLE_SAFE_ASSIGNABLE_ROLES", text)
		self.assertIn("page_length = min(max(cint(page_length) or 20, 1), 50)", text.replace("\n", ""))

	def test_edgesuite_role_editor_routes_search_through_delegation_guard(self):
		provider = (ROOT / "vetedge/services/administration_workspace.py").read_text(encoding="utf-8")
		page = (
			ROOT
			/ "vetedge/veterinary/page/vetedge_administration/vetedge_administration.js"
		).read_text(encoding="utf-8")
		self.assertIn(
			"from vetedge.services.role_bundle_security import search_assignable_role_options",
			provider,
		)
		self.assertIn("return search_assignable_role_options(query=query, page_length=page_length)", provider)
		self.assertIn(
			'link: "vetedge.services.administration_workspace.search_administration_link"',
			page,
		)
		self.assertIn("VETEDGE_ADMIN_API.link", page)
		self.assertIn('fieldname: "role"', page)


if __name__ == "__main__":
	unittest.main()
