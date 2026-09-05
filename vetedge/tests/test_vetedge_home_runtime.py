from __future__ import annotations

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge.services.home import get_home_payload


class TestVetEdgeHomeRuntime(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	def ensure_user(self, email: str, roles: tuple[str, ...]) -> str:
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "VHOME",
					"enabled": 1,
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		user = frappe.get_doc("User", email)
		existing = {row.role for row in user.get("roles") or []}
		for role in roles:
			if role not in existing:
				user.add_roles(role)
		return email

	def test_administrator_home_payload_executes_on_installed_site(self):
		payload = get_home_payload()
		self.assertEqual(payload["primary_persona"]["key"], "administrator")
		self.assertIn("context", payload)
		self.assertIn("metrics", payload)
		self.assertIn("attention", payload)
		self.assertIn("quick_actions", payload)

	def test_doctor_starter_support_role_does_not_add_accounts_persona(self):
		user = self.ensure_user(
			"vhome-doctor@example.com",
			("VetEdge Doctor", "Desk User", "Accounts User", "Sales User", "Stock User"),
		)
		frappe.set_user(user)
		payload = get_home_payload()
		persona_keys = {persona["key"] for persona in payload["personas"]}
		self.assertEqual(payload["primary_persona"]["key"], "doctor")
		self.assertIn("doctor", persona_keys)
		self.assertNotIn("accounts", persona_keys)

	def test_front_desk_starter_support_role_does_not_add_accounts_persona(self):
		user = self.ensure_user(
			"vhome-frontdesk@example.com",
			("VetEdge Front Desk", "Desk User", "Accounts User", "Sales User"),
		)
		frappe.set_user(user)
		payload = get_home_payload()
		persona_keys = {persona["key"] for persona in payload["personas"]}
		self.assertEqual(payload["primary_persona"]["key"], "front-desk")
		self.assertNotIn("accounts", persona_keys)

	def test_accounts_user_without_vetedge_primary_role_uses_accounts_fallback(self):
		user = self.ensure_user(
			"vhome-accounts@example.com",
			("Desk User", "Accounts User"),
		)
		frappe.set_user(user)
		payload = get_home_payload()
		self.assertEqual(payload["primary_persona"]["key"], "accounts")
