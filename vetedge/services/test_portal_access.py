from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from werkzeug.routing import RequestRedirect

from vetedge.services.portal_access import (
	block_owner_portal_desk_access,
	ensure_owner_portal_user_for_patient,
	get_customers_for_user,
	get_owner_portal_redirect_path,
	get_vetedge_website_user_home_page,
	has_sales_invoice_permission,
	require_internal_user,
	validate_owner_customer_access,
	validate_owner_invoice_access,
	validate_owner_patient_access,
)


class TestPortalAccess(TestCase):
	def test_owner_customers_prefer_explicit_portal_links_over_contact_fallback(self):
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

		self.assertEqual(customers, ["CUST-PORTAL"])

	def test_owner_customers_fall_back_to_contact_links_without_portal_mapping(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return []
			if doctype == "Contact":
				return ["CONTACT-001"]
			if doctype == "Dynamic Link":
				return ["CUST-CONTACT"]
			return []

		frappe_stub = make_frappe_stub(get_all=get_all)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			customers = get_customers_for_user("owner@example.com")

		self.assertEqual(customers, ["CUST-CONTACT"])

	def test_owner_customers_use_contact_user_links_before_email_fallback(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return []
			if doctype == "Contact" and filters == {"user": "owner@example.com"}:
				return ["CONTACT-USER"]
			if doctype == "Dynamic Link" and filters.get("parent") == ["in", ["CONTACT-USER"]]:
				return ["CUST-USER"]
			raise AssertionError((doctype, filters, pluck))

		frappe_stub = make_frappe_stub(get_all=get_all)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			customers = get_customers_for_user("owner@example.com")

		self.assertEqual(customers, ["CUST-USER"])

	def test_owner_customers_do_not_expand_to_multiple_email_matches(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return []
			if doctype == "Contact" and filters == {"user": "owner@example.com"}:
				return []
			if doctype == "Contact" and filters == {"email_id": "owner@example.com"}:
				return ["CONTACT-001", "CONTACT-002"]
			if doctype == "Dynamic Link" and filters.get("parent") == ["in", ["CONTACT-001", "CONTACT-002"]]:
				return ["CUST-001", "CUST-002"]
			raise AssertionError((doctype, filters, pluck))

		frappe_stub = make_frappe_stub(get_all=get_all)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			customers = get_customers_for_user("owner@example.com")

		self.assertEqual(customers, [])

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
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda doctype, name=None, fieldname=None, **kwargs: "Website User"
				if doctype == "User"
				else 0,
			),
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
			values.save = lambda ignore_permissions=False: values
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
		self.assertTrue(result["owner_role_added"])
		self.assertFalse(result["user_type_changed"])
		self.assertFalse(result["role_removed"])
		self.assertEqual(
			result["post_link_hardening"],
			{"owner_role_added": False, "role_removed": False, "user_type_changed": False},
		)
		self.assertTrue(result["portal_link_added"])
		self.assertEqual(inserted_users[0].user_type, "Website User")
		self.assertEqual(added_roles, ["VetEdge Portal User"])
		self.assertEqual(customer.portal_users[0].user, "jane@example.com")
		self.assertEqual(saved_customers, [customer])

	def test_existing_non_desk_customer_user_is_downgraded_to_website_user(self):
		customer = frappe._dict(
			name="CUST-001",
			customer_name="Jane Owner",
			email_id="jane@example.com",
			portal_users=[],
		)
		customer.append = lambda table, row: customer[table].append(frappe._dict(row))
		customer.save = lambda ignore_permissions=False: customer
		saved = []
		user_doc = frappe._dict(
			name="jane@example.com",
			email="jane@example.com",
			enabled=1,
			user_type="System User",
			roles=[frappe._dict(role="Customer")],
		)
		removed_roles = []
		added_roles = []
		user_doc.add_roles = lambda *roles: added_roles.extend(roles)
		user_doc.remove_roles = lambda *roles: removed_roles.extend(roles)
		user_doc.save = lambda ignore_permissions=False: saved.append(user_doc) or user_doc

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "Veterinary Patient":
				return frappe._dict(name="VP-001", patient_name="Bingo", primary_owner="CUST-001")
			if doctype == "Role":
				return 0
			return None

		def get_doc(*args, **kwargs):
			if args == ("Customer", "CUST-001"):
				return customer
			if args == ("User", "jane@example.com"):
				return user_doc
			raise AssertionError(args)

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=get_value,
			),
			get_doc=get_doc,
			get_roles=lambda *args, **kwargs: ["VetEdge Front Desk"],
		)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			result = ensure_owner_portal_user_for_patient("VP-001")

		self.assertTrue(result["user_type_changed"])
		self.assertTrue(result["owner_role_added"])
		self.assertTrue(result["role_removed"])
		self.assertEqual(
			result["post_link_hardening"],
			{"owner_role_added": True, "role_removed": True, "user_type_changed": False},
		)
		self.assertEqual(user_doc.user_type, "Website User")
		self.assertEqual(added_roles, ["VetEdge Portal User", "VetEdge Portal User"])
		self.assertEqual(removed_roles, ["Customer", "Customer"])
		self.assertEqual(saved, [user_doc, user_doc, user_doc])

	def test_owner_portal_user_creation_requires_staff_role(self):
		frappe_stub = make_frappe_stub(get_roles=lambda *args, **kwargs: ["Customer"])

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			self.assertRaises(
				frappe.PermissionError,
				ensure_owner_portal_user_for_patient,
				"VP-001",
				email="jane@example.com",
			)

	def test_require_internal_user_blocks_owner_portal_user(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return ["CUST-001"]
			return []

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "User":
				return "Website User"
			if doctype == "Role":
				return 0
			return None

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			get_roles=lambda *args, **kwargs: ["Customer"],
			db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=get_value),
		)

		with (
			patch("vetedge.services.portal_access.frappe", frappe_stub),
			patch("vetedge.services.portal_access._", lambda value: value),
		):
			self.assertRaises(frappe.PermissionError, require_internal_user)

	def test_portal_invoice_permission_allows_read_but_not_write(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return ["CUST-001"]
			return []

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "User":
				return "Website User"
			if doctype == "Role":
				return 0
			if doctype == "Sales Invoice":
				return frappe._dict(
					name="SINV-001",
					customer="CUST-001",
					posting_date="2026-04-20",
					status="Unpaid",
					outstanding_amount=100,
					grand_total=100,
					currency="NGN",
					docstatus=1,
				)
			return None

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			get_roles=lambda *args, **kwargs: ["Customer"],
			db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=get_value),
		)

		with patch("vetedge.services.portal_access.frappe", frappe_stub):
			self.assertTrue(has_sales_invoice_permission("SINV-001", user="owner@example.com", permission_type="read"))
			self.assertFalse(has_sales_invoice_permission("SINV-001", user="owner@example.com", permission_type="write"))

	def test_owner_portal_user_is_redirected_to_portal_home_from_internal_route(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return ["CUST-001"]
			return []

		def get_value(doctype, name=None, fieldname=None, **kwargs):
			if doctype == "User":
				return "Website User"
			if doctype == "Role":
				return 0
			return None

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			get_roles=lambda *args, **kwargs: [],
			db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=get_value),
		)
		frappe_stub.local.request = SimpleNamespace(path="/app/veterinary-financial-dashboard")

		with (
			patch("vetedge.services.portal_access.frappe", frappe_stub),
			patch("vetedge.services.portal_access.get_portal_settings", return_value={"enable_owner_portal": True}),
		):
			self.assertEqual(
				get_owner_portal_redirect_path("/app/veterinary-financial-dashboard", user="owner@example.com"),
				"/vetedge_portal",
			)

	def test_owner_portal_user_is_redirected_from_login_to_portal_home(self):
		def get_all(doctype, filters=None, pluck=None, **kwargs):
			if doctype == "Portal User":
				return ["CUST-001"]
			return []

		def get_value(doctype, name=None, fieldname=None, **kwargs):
			if doctype == "User":
				return "Website User"
			if doctype == "Role":
				return 0
			return None

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			get_roles=lambda *args, **kwargs: [],
			db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=get_value),
		)
		frappe_stub.local.request = SimpleNamespace(path="/login")

		with (
			patch("vetedge.services.portal_access.frappe", frappe_stub),
			patch("vetedge.services.portal_access.get_portal_settings", return_value={"enable_owner_portal": True}),
		):
			self.assertRaises(RequestRedirect, block_owner_portal_desk_access)
			self.assertEqual(frappe_stub.local.response["location"], "/vetedge_portal")


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
		local=SimpleNamespace(flags=SimpleNamespace(), request=None, response={}),
		Redirect=frappe.Redirect,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub
