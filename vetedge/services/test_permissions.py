from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.permissions import (
	can_access_branch_data,
	can_dispense,
	can_initiate_payment,
	validate_branch_user_assignment,
	validate_branch_practitioner_assignment,
	validate_consultation_clinical_permissions,
)


class TestPermissions(TestCase):
	def test_branch_access_is_blocked_for_unassigned_internal_user(self):
		with (
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Branch A"]),
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				can_access_branch_data,
				"doctor@example.com",
				"Branch B",
				raise_exception=True,
			)

	def test_doctor_can_dispense(self):
		consultation = frappe._dict(name="VCON-001", doctype="Veterinary Consultation", service_branch="Main")

		with (
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Doctor"}),
			patch("vetedge.services.permissions.can_access_branch_data", return_value=True),
		):
			self.assertTrue(
				can_dispense(
					"doctor@example.com",
					consultation,
					raise_exception=True,
				)
			)

	def test_non_dispensary_non_doctor_cannot_dispense(self):
		consultation = frappe._dict(name="VCON-001", doctype="Veterinary Consultation", service_branch="Main")

		with (
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.user_has_any_role", return_value=False),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Front Desk"}),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				can_dispense,
				"frontdesk@example.com",
				consultation,
				raise_exception=True,
			)

	def test_internal_payment_requires_accounts_when_doctor_collection_disabled(self):
		settings = SimpleNamespace(allow_doctor_collect_payment=False)

		with (
			patch("vetedge.services.permissions.can_view_invoice", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Doctor"}),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
			patch("vetedge.services.billing.get_consultation_billing_settings", return_value=settings),
		):
			self.assertRaises(
				frappe.PermissionError,
				can_initiate_payment,
				"doctor@example.com",
				"SINV-001",
				mode="internal",
				raise_exception=True,
			)

	def test_doctor_can_collect_payment_when_setting_allows_it(self):
		settings = SimpleNamespace(allow_doctor_collect_payment=True)

		with (
			patch("vetedge.services.permissions.can_view_invoice", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Doctor"}),
			patch("vetedge.services.billing.get_consultation_billing_settings", return_value=settings),
		):
			self.assertTrue(
				can_initiate_payment(
					"doctor@example.com",
					"SINV-001",
					mode="internal",
					raise_exception=True,
				)
			)

	def test_only_doctor_can_capture_clinical_rows(self):
		doc = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			diagnoses=[frappe._dict(diagnosis="DIAG-001")],
			planned_treatments=[],
		)

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Front Desk"}),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				validate_consultation_clinical_permissions,
				doc,
				"user@example.com",
			)

	def test_branch_practitioner_assignment_requires_doctor_role(self):
		doc = frappe._dict(practitioner="nurse@example.com", branch="Main", name="BPA-0001")

		with (
			patch("vetedge.services.permissions.get_user_roles", return_value={"Veterinary Nurse"}),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_branch_practitioner_assignment, doc)

	def test_branch_user_assignment_requires_system_user(self):
		doc = frappe._dict(user="owner@example.com", branch="Main", name="BUA-0001")
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(get_value=lambda *args, **kwargs: "Website User"),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.ValidationError)()),
			ValidationError=frappe.ValidationError,
		)

		with (
			patch("vetedge.services.permissions.frappe", frappe_stub),
		):
			self.assertRaises(frappe.ValidationError, validate_branch_user_assignment, doc)
