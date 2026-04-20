from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.portal_access import (
	ensure_owner_portal_user_for_patient,
	get_customers_for_user,
	get_vetedge_website_user_home_page,
	validate_owner_customer_access,
	validate_owner_invoice_access,
	validate_owner_patient_access,
)


class TestPortalAccess(TestCase):
	def test_owner_customers_resolve_from_portal_user_and_contact(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return ["CUST-PORTAL"]
			if doctype == "Contact":
				return ["CONTACT-001"]
			if doctype == "Dynamic Link":
				return ["CUST-CONTACT"]
			return []

		frappe_stub = make_frappe_stub(get_all=get_all)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			customers = get_customers_for_user("owner@example.com")

		self.assertEqual(customers, ["CUST-CONTACT", "CUST-PORTAL"])

	def test_customer_access_blocks_unowned_customer(self):
		frappe_stub = make_frappe_stub()

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			self.assertRaises(
				frappe.PermissionError,
				validate_owner_customer_access,
				"CUST-OTHER",
				{"customers": ["CUST-001"]},
			)

	def test_patient_access_uses_primary_owner(self):
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: "CUST-001",
			)
		)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			validate_owner_patient_access("VP-001", {"customers": ["CUST-001"]})

	def test_invoice_access_blocks_other_customer_invoice(self):
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: frappe._dict(
					name="SINV-001",
					customer="CUST-OTHER",
					posting_date="2026-04-20",
					status="Unpaid",
					outstanding_amount=100,
					grand_total=100,
					currency="NGN",
					docstatus=1,
				),
			)
		)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			self.assertRaises(
				frappe.PermissionError,
				validate_owner_invoice_access,
				"SINV-001",
				{"customers": ["CUST-001"]},
			)

	def test_owner_portal_user_home_page_routes_to_owner_portal(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return ["CUST-001"]
			return []

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			get_roles=lambda user=None: ["Customer"],
		)

		with (
			patch("vetedge.services.portal_access.frappe", frappe_stub),
			patch(
				"vetedge.services.portal_access.get_portal_settings",
				return_value={"enable_owner_portal": True},
			),
		):
			self.assertEqual(get_vetedge_website_user_home_page("owner@example.com"), "vetedge_portal")

	def test_non_customer_user_home_page_is_not_overridden(self):
		frappe_stub = make_frappe_stub(
			get_roles=lambda user=None: ["Accounts User"],
		)

		with (
			patch("vetedge.services.portal_access.frappe", frappe_stub),
			patch(
				"vetedge.services.portal_access.get_portal_settings",
				return_value={"enable_owner_portal": True},
			),
		):
			self.assertIsNone(get_vetedge_website_user_home_page("staff@example.com"))

	def test_staff_can_create_and_link_owner_portal_user_from_patient(self):
		inserted_users = []
		saved_customers = []
		added_roles = []

		customer = frappe._dict(
			name="CUST-001",
			customer_name="Jane Owner",
			email_id="jane@example.com",
			portal_users=[],
		)
		customer.append = lambda table, row: customer[table].append(frappe._dict(row))
		customer.save = lambda ignore_permissions=False: saved_customers.append(customer) or customer

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "Veterinary Patient":
				return frappe._dict(name="VP-001", patient_name="Bingo", primary_owner="CUST-001")
			return None

		def exists(doctype, name=None, **kwargs):
			if doctype == "User":
				return False
			return True

		def get_doc(*args, **kwargs):
			if args == ("Customer", "CUST-001"):
				return customer
			values = frappe._dict(args[0])
			values.name = values.email
			values.roles = []
			values.insert = lambda ignore_permissions=False: inserted_users.append(values) or values
			values.add_roles = lambda *roles: added_roles.extend(roles)
			return values

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(exists=exists, get_value=get_value),
			get_doc=get_doc,
			get_roles=lambda *args, **kwargs: ["VetEdge Front Desk"],
		)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			result = ensure_owner_portal_user_for_patient("VP-001")

		self.assertEqual(result["user"], "jane@example.com")
		self.assertTrue(result["user_created"])
		self.assertTrue(result["role_added"])
		self.assertTrue(result["portal_link_added"])
		self.assertEqual(inserted_users[0].user_type, "Website User")
		self.assertEqual(added_roles, ["Customer"])
		self.assertEqual(customer.portal_users[0].user, "jane@example.com")
		self.assertEqual(saved_customers, [customer])

	def test_owner_portal_user_creation_requires_staff_role(self):
		frappe_stub = make_frappe_stub(get_roles=lambda *args, **kwargs: ["Customer"])

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			self.assertRaises(
				frappe.PermissionError,
				ensure_owner_portal_user_for_patient,
				"VP-001",
				email="jane@example.com",
			)


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=lambda *args, **kwargs: None),
		get_all=lambda *args, **kwargs: [],
		get_roles=lambda *args, **kwargs: [],
		throw=throw,
		PermissionError=frappe.PermissionError,
		ValidationError=frappe.ValidationError,
		session=SimpleNamespace(user="owner@example.com"),
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub
