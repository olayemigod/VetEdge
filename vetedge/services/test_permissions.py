from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.permissions import (
	can_access_patient,
	can_access_branch_data,
	can_dispense,
	can_enter_lab_results,
	can_review_lab_results,
	get_invoice_access_diagnostic,
	has_veterinary_appointment_permission,
	can_request_lab_tests,
	has_veterinary_patient_permission,
	get_veterinary_guest_booking_request_query,
	get_veterinary_appointment_query,
	get_veterinary_patient_query,
	has_veterinary_consultation_permission,
	has_veterinary_lab_order_permission,
	has_sales_invoice_permission,
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

	def test_doctor_cannot_confirm_dispensary(self):
		consultation = frappe._dict(name="VCON-001", doctype="Veterinary Consultation", service_branch="Main")

		with (
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Doctor"}),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				can_dispense,
				"doctor@example.com",
				consultation,
				raise_exception=True,
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

	def test_doctor_can_request_lab_tests(self):
		consultation = frappe._dict(name="VCON-001", doctype="Veterinary Consultation")

		with (
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Doctor"}),
		):
			self.assertTrue(can_request_lab_tests("doctor@example.com", consultation, raise_exception=True))

	def test_front_desk_cannot_enter_lab_results(self):
		lab_order = frappe._dict(name="VLAB-001", doctype="Veterinary Lab Order")

		with (
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Front Desk"}),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				can_enter_lab_results,
				"frontdesk@example.com",
				lab_order,
				raise_exception=True,
			)

	def test_doctor_can_enter_lab_results(self):
		lab_order = frappe._dict(name="VLAB-001", doctype="Veterinary Lab Order")

		with (
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Doctor"}),
		):
			self.assertTrue(can_enter_lab_results("doctor@example.com", lab_order, raise_exception=True))

	def test_lab_technician_cannot_review_lab_results(self):
		lab_order = frappe._dict(name="VLAB-001", doctype="Veterinary Lab Order")

		with (
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.get_user_roles", return_value={"Lab Technician"}),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				can_review_lab_results,
				"lab@example.com",
				lab_order,
				raise_exception=True,
			)

	def test_new_lab_order_create_permission_defers_to_role_permission_manager(self):
		lab_order = frappe._dict(doctype="Veterinary Lab Order", service_branch="Main Branch")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
		):
			self.assertIsNone(
				has_veterinary_lab_order_permission(
					lab_order,
					user="doctor@example.com",
					permission_type="create",
				)
			)

	def test_consultation_create_permission_defers_to_role_permission_manager(self):
		consultation = frappe._dict(doctype="Veterinary Consultation", service_branch="Main Branch")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
		):
			self.assertIsNone(
				has_veterinary_consultation_permission(
					consultation,
					user="doctor@example.com",
					permission_type="create",
				)
			)

	def test_new_patient_form_access_defers_to_role_permission_manager(self):
		patient = frappe._dict(doctype="Veterinary Patient", name="new-veterinary-patient-abc", default_branch="Main Branch")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
			patch("vetedge.services.permissions._document_exists", return_value=False),
		):
			self.assertTrue(
				has_veterinary_patient_permission(
					patient,
					user="doctor@example.com",
					permission_type="read",
				)
			)

	def test_patient_access_is_global_when_restriction_disabled(self):
		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.is_patient_branch_restriction_enabled", return_value=False),
		):
			self.assertTrue(
				can_access_patient(
					"doctor@example.com",
					"VP-001",
					raise_exception=True,
				)
			)

	def test_patient_read_permission_is_global_when_restriction_disabled(self):
		patient = frappe._dict(name="VP-001", doctype="Veterinary Patient", default_branch="Branch B")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.is_patient_branch_restriction_enabled", return_value=False),
		):
			self.assertTrue(
				has_veterinary_patient_permission(
					patient,
					user="doctor@example.com",
					permission_type="read",
				)
			)

	def test_patient_query_is_disabled_when_restriction_is_off(self):
		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.is_patient_branch_restriction_enabled", return_value=False),
		):
			query = get_veterinary_patient_query("doctor@example.com")

		self.assertIsNone(query)

	def test_patient_access_is_branch_scoped_when_restriction_enabled(self):
		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.is_patient_branch_restriction_enabled", return_value=True),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Branch A"]),
			patch("vetedge.services.permissions.frappe.db.get_value", return_value="Branch B"),
			patch("vetedge.services.permissions.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				can_access_patient,
				"doctor@example.com",
				"VP-001",
				raise_exception=True,
			)

	def test_patient_read_permission_is_blocked_when_restriction_enabled_for_other_branch(self):
		patient = frappe._dict(name="VP-001", doctype="Veterinary Patient", default_branch="Branch B")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.is_patient_branch_restriction_enabled", return_value=True),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Branch A"]),
			patch("vetedge.services.permissions._document_exists", return_value=True),
		):
			self.assertFalse(
				has_veterinary_patient_permission(
					patient,
					user="doctor@example.com",
					permission_type="read",
				)
			)

	def test_patient_query_is_branch_scoped_when_restriction_enabled(self):
		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.is_patient_branch_restriction_enabled", return_value=True),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
			patch(
				"vetedge.services.permissions.frappe",
				SimpleNamespace(db=SimpleNamespace(escape=lambda value: f"'{value}'")),
			),
		):
			query = get_veterinary_patient_query("doctor@example.com")

		self.assertIn("IFNULL(`tabVeterinary Patient`.`default_branch`, '') = ''", query)
		self.assertIn("`tabVeterinary Patient`.`default_branch` in ('Main Branch')", query)

	def test_system_manager_bypasses_patient_restriction(self):
		patient = frappe._dict(name="VP-001", doctype="Veterinary Patient", default_branch="Branch B")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=True),
			patch("vetedge.services.permissions.is_patient_branch_restriction_enabled", return_value=True),
		):
			self.assertTrue(
				has_veterinary_patient_permission(
					patient,
					user="admin@example.com",
					permission_type="read",
				)
			)

	def test_new_appointment_form_access_defers_to_role_permission_manager(self):
		appointment = frappe._dict(doctype="Veterinary Appointment", name="new-veterinary-appointment-abc", branch="Main Branch")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
			patch("vetedge.services.permissions._document_exists", return_value=False),
		):
			self.assertIsNone(
				has_veterinary_appointment_permission(
					appointment,
					user="doctor@example.com",
					permission_type="read",
				)
			)

	def test_consultation_read_permission_is_allowed_for_assigned_branch(self):
		consultation = frappe._dict(name="VCON-001", doctype="Veterinary Consultation", service_branch="Main Branch")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
			patch("vetedge.services.permissions._document_exists", return_value=True),
		):
			self.assertTrue(
				has_veterinary_consultation_permission(
					consultation,
					user="doctor@example.com",
					permission_type="read",
				)
			)

	def test_consultation_read_permission_is_blocked_for_other_branch(self):
		consultation = frappe._dict(name="VCON-001", doctype="Veterinary Consultation", service_branch="Branch B")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Branch A"]),
			patch("vetedge.services.permissions._document_exists", return_value=True),
		):
			self.assertFalse(
				has_veterinary_consultation_permission(
					consultation,
					user="doctor@example.com",
					permission_type="read",
				)
			)

	def test_admin_consultation_access_bypasses_branch_scope(self):
		consultation = frappe._dict(name="VCON-001", doctype="Veterinary Consultation", service_branch="Branch B")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=True),
		):
			self.assertIsNone(
				has_veterinary_consultation_permission(
					consultation,
					user="admin@example.com",
					permission_type="read",
				)
			)

	def test_internal_sales_invoice_read_permission_allows_erpnext_to_continue(self):
		invoice = frappe._dict(name="ACC-SINV-2026-00028", doctype="Sales Invoice", branch="Main Branch")

		with patch("vetedge.services.permissions.is_portal_owner_user", return_value=False):
			self.assertTrue(
				has_sales_invoice_permission(
					invoice,
					user="doctor@example.com",
					permission_type="read",
				)
			)

	def test_internal_sales_invoice_create_permission_allows_erpnext_to_continue(self):
		invoice = frappe._dict(doctype="Sales Invoice", branch="Main Branch")

		with patch("vetedge.services.permissions.is_portal_owner_user", return_value=False):
			self.assertTrue(
				has_sales_invoice_permission(
					invoice,
					user="doctor@example.com",
					permission_type="create",
				)
			)

	def test_internal_sales_invoice_print_permission_allows_when_no_branch_restriction_applies(self):
		invoice = frappe._dict(name="ACC-SINV-2026-00028", doctype="Sales Invoice", branch="Main Branch")

		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.has_document_permission", return_value=None),
			patch("vetedge.services.permissions.frappe.get_meta", return_value=SimpleNamespace(has_field=lambda field: field == "branch")),
		):
			self.assertTrue(
				has_sales_invoice_permission(
					invoice,
					user="doctor@example.com",
					permission_type="print",
				)
			)

	def test_branch_scoped_query_allows_records_with_blank_branch(self):
		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
			patch(
				"vetedge.services.permissions.frappe",
				SimpleNamespace(db=SimpleNamespace(escape=lambda value: f"'{value}'")),
			),
		):
			query = get_veterinary_appointment_query("doctor@example.com")

		self.assertIn("IFNULL(`tabVeterinary Appointment`.`branch`, '') = ''", query)
		self.assertIn("`tabVeterinary Appointment`.`branch` in ('Main Branch')", query)

	def test_guest_booking_request_query_is_branch_scoped(self):
		with (
			patch("vetedge.services.permissions.is_portal_owner_user", return_value=False),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main Branch"]),
			patch(
				"vetedge.services.permissions.frappe",
				SimpleNamespace(db=SimpleNamespace(escape=lambda value: f"'{value}'")),
			),
		):
			query = get_veterinary_guest_booking_request_query("doctor@example.com")

		self.assertIn("IFNULL(`tabVeterinary Guest Booking Request`.`preferred_branch`, '') = ''", query)
		self.assertIn("`tabVeterinary Guest Booking Request`.`preferred_branch` in ('Main Branch')", query)

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

	def test_invoice_access_diagnostic_reports_branch_restriction(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: "Branch B",
			),
			get_meta=lambda *args, **kwargs: SimpleNamespace(has_field=lambda field: field == "branch"),
		)

		with (
			patch("vetedge.services.permissions.frappe", frappe_stub),
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.can_view_invoice", return_value=False),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Branch A"]),
			patch("vetedge.services.permissions.user_has_global_branch_access", return_value=False),
		):
			result = get_invoice_access_diagnostic("doctor@example.com", "ACC-SINV-2026-00029")

		self.assertFalse(result["allowed"])
		self.assertEqual(result["category"], "branch_restriction")
		self.assertIn("VetEdge branch restriction", result["message"])

	def test_invoice_access_diagnostic_reports_role_permission_block(self):
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=lambda *args, **kwargs: "Main"),
			get_meta=lambda *args, **kwargs: SimpleNamespace(has_field=lambda field: field == "branch"),
			permissions=SimpleNamespace(
				has_permission=lambda *args, **kwargs: False,
				_pop_debug_log=lambda: ["User doctor@example.com does not have doctype access via role permission for document Sales Invoice"],
			),
		)

		with (
			patch("vetedge.services.permissions.frappe", frappe_stub),
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.can_view_invoice", return_value=True),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main"]),
			patch("vetedge.services.permissions.get_user_roles", return_value={"VetEdge Doctor"}),
			patch("vetedge.services.permissions.get_sales_invoice_read_roles", return_value=["Sales User", "Accounts User"]),
		):
			result = get_invoice_access_diagnostic("doctor@example.com", "ACC-SINV-2026-00029")

		self.assertFalse(result["allowed"])
		self.assertEqual(result["category"], "erpnext_role_permission")
		self.assertIn("Runtime user roles: VetEdge Doctor", result["message"])
		self.assertIn("Sales Invoice read roles configured on this site:", result["message"])
		self.assertIn("Sales User", result["message"])
		self.assertIn("Accounts User", result["message"])
		self.assertIn("Matching read roles on the current user: none", result["message"])

	def test_invoice_access_diagnostic_reports_user_permission_block(self):
		log_sets = [
			[],
			["User doesn't have access to this document because of User Permissions"],
		]
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=lambda *args, **kwargs: "Main"),
			get_meta=lambda *args, **kwargs: SimpleNamespace(has_field=lambda field: field == "branch"),
			permissions=SimpleNamespace(
				has_permission=lambda *args, **kwargs: True if kwargs.get("doc") is None else False,
				_pop_debug_log=lambda: log_sets.pop(0),
			),
		)

		with (
			patch("vetedge.services.permissions.frappe", frappe_stub),
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.can_view_invoice", return_value=True),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main"]),
		):
			result = get_invoice_access_diagnostic("doctor@example.com", "ACC-SINV-2026-00029")

		self.assertFalse(result["allowed"])
		self.assertEqual(result["category"], "user_permission")
		self.assertIn("User Permission", result["message"])

	def test_invoice_access_diagnostic_does_not_misclassify_successful_role_evaluation(self):
		log_sets = [
			["User has following permissions using role permission system: {'read': 1}"],
			["User has following permissions using role permission system: {'read': 1}", "Document is shared with user for read? False"],
		]
		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=lambda *args, **kwargs: "Main"),
			get_meta=lambda *args, **kwargs: SimpleNamespace(has_field=lambda field: field == "branch"),
			permissions=SimpleNamespace(
				has_permission=lambda *args, **kwargs: True if kwargs.get("doc") is None else False,
				_pop_debug_log=lambda: log_sets.pop(0),
			),
		)

		with (
			patch("vetedge.services.permissions.frappe", frappe_stub),
			patch("vetedge.services.permissions.is_internal_staff_user", return_value=True),
			patch("vetedge.services.permissions.can_view_invoice", return_value=True),
			patch("vetedge.services.permissions.get_assigned_branches", return_value=["Main"]),
		):
			result = get_invoice_access_diagnostic("doctor@example.com", "ACC-SINV-2026-00029")

		self.assertFalse(result["allowed"])
		self.assertEqual(result["category"], "erpnext_permission")

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
