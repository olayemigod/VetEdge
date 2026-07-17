from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.role_bundles import (
	apply_role_bundle,
	ensure_existing_internal_users_have_starter_bundle_roles,
	ensure_user_has_roles,
)


class TestRoleBundles(TestCase):
	def test_starter_bundles_include_required_erpnext_roles(self):
		from vetedge.services.role_bundles import STARTER_ROLE_BUNDLES

		self.assertEqual(
			STARTER_ROLE_BUNDLES["VetEdge Administrator"],
			[
				"VetEdge Administrator",
				"Desk User",
				"Workspace Manager",
				"Report Manager",
				"Accounts User",
				"Sales User",
				"Stock User",
			],
		)
		self.assertEqual(
			STARTER_ROLE_BUNDLES["Accounts/Cashier"],
			["Accounts/Cashier", "Desk User", "Accounts User", "Sales User"],
		)
		self.assertEqual(
			STARTER_ROLE_BUNDLES["Dispensary User"],
			["Dispensary User", "Desk User", "Accounts User", "Stock User", "Sales User"],
		)
		self.assertEqual(
			STARTER_ROLE_BUNDLES["Veterinary Doctor"],
			["VetEdge Doctor", "Desk User", "Accounts User", "Sales User", "Stock User"],
		)
		self.assertEqual(
			STARTER_ROLE_BUNDLES["Front Desk"],
			["VetEdge Front Desk", "Desk User", "Accounts User", "Sales User"],
		)
		self.assertEqual(
			STARTER_ROLE_BUNDLES["Grooming Staff"],
			["VetEdge Groomer", "Desk User"],
		)
		self.assertEqual(
			STARTER_ROLE_BUNDLES["Branch Manager"],
			["Branch Manager", "Desk User", "Accounts User", "Sales User", "Stock User"],
		)

	def test_duplicate_roles_in_bundle_are_rejected(self):
		doc = frappe._dict(
			bundle_name="Veterinary Doctor",
			roles=[frappe._dict(role="VetEdge Doctor"), frappe._dict(role="VetEdge Doctor")],
			get=lambda key, default=None: doc[key] if key in doc else default,
		)

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda doctype, name: True),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)()),
			ValidationError=frappe.ValidationError,
		)

		with patch("vetedge.services.permissions.frappe", frappe_stub):
			from vetedge.services.permissions import validate_role_bundle

			self.assertRaises(frappe.ValidationError, validate_role_bundle, doc)

	def test_apply_role_bundle_adds_only_missing_roles(self):
		bundle = frappe._dict(
			bundle_name="Accounts/Cashier",
			is_active=1,
			get=lambda key, default=None: bundle[key] if key in bundle else default,
			roles=[
				frappe._dict(role="Accounts/Cashier"),
				frappe._dict(role="Desk User"),
				frappe._dict(role="Accounts User"),
				frappe._dict(role="Sales User"),
			],
		)
		added = []
		user_doc = frappe._dict(
			roles=[frappe._dict(role="Accounts/Cashier")],
			add_roles=lambda role: added.append(role),
			get=lambda key, default=None: user_doc[key] if key in user_doc else default,
		)

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda doctype, name: True),
			get_doc=lambda doctype, name: bundle if doctype == "Veterinary Role Bundle" else user_doc,
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)()),
			ValidationError=frappe.ValidationError,
		)

		with (
			patch("vetedge.services.role_bundles.frappe", frappe_stub),
			patch("vetedge.services.role_bundles.can_apply_role_bundle"),
			patch("vetedge.services.role_bundles.log_operational_event"),
		):
			result = apply_role_bundle("Accounts/Cashier", "cashier@example.com", acting_user="admin@example.com")

		self.assertEqual(added, ["Desk User", "Accounts User", "Sales User"])
		self.assertEqual(result["added_roles"], ["Desk User", "Accounts User", "Sales User"])
		self.assertEqual(result["already_present_roles"], ["Accounts/Cashier"])

	def test_apply_role_bundle_is_blocked_for_unauthorized_user(self):
		with patch("vetedge.services.role_bundles.can_apply_role_bundle", side_effect=frappe.PermissionError):
			self.assertRaises(
				frappe.PermissionError,
				apply_role_bundle,
				"Veterinary Doctor",
				"doctor@example.com",
				acting_user="frontdesk@example.com",
			)

	def test_ensure_user_has_roles_adds_missing_only(self):
		added = []
		user_doc = frappe._dict(
			roles=[frappe._dict(role="VetEdge Doctor"), frappe._dict(role="Desk User")],
			add_roles=lambda role: added.append(role),
			get=lambda key, default=None: user_doc[key] if key in user_doc else default,
		)
		frappe_stub = SimpleNamespace(get_doc=lambda doctype, name: user_doc)

		with patch("vetedge.services.role_bundles.frappe", frappe_stub):
			result = ensure_user_has_roles(
				"doctor@example.com",
				["VetEdge Doctor", "Desk User", "Accounts User", "Sales User"],
			)

		self.assertEqual(result, ["Accounts User", "Sales User"])
		self.assertEqual(added, ["Accounts User", "Sales User"])

	def test_existing_doctor_users_pick_up_invoice_roles_on_sync(self):
		added = []
		user_doc = frappe._dict(
			roles=[frappe._dict(role="VetEdge Doctor"), frappe._dict(role="Desk User")],
			add_roles=lambda role: added.append(role),
			get=lambda key, default=None: user_doc[key] if key in user_doc else default,
		)

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda doctype, name: doctype in {"DocType", "Has Role"}),
			get_all=lambda doctype, filters=None, pluck=None: ["doctor@example.com"],
			get_doc=lambda doctype, name: user_doc,
		)

		with patch("vetedge.services.role_bundles.frappe", frappe_stub):
			ensure_existing_internal_users_have_starter_bundle_roles()

		self.assertIn("Accounts User", added)
		self.assertIn("Sales User", added)
