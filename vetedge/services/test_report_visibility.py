from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.report_visibility import (
	normalize_dashboard_filters,
	normalize_report_filters,
	validate_dashboard_access,
	validate_report_access,
)


class TestReportVisibility(TestCase):
	def test_validate_report_access_blocks_unauthorized_role(self):
		with (
			patch("vetedge.services.report_visibility._", side_effect=lambda value: value),
			patch("vetedge.services.report_visibility.is_portal_owner_user", return_value=False),
			patch("vetedge.services.report_visibility.get_user_roles", return_value={"VetEdge Front Desk"}),
			patch("vetedge.services.report_visibility.frappe.throw", side_effect=frappe.PermissionError),
		):
			self.assertRaises(
				frappe.PermissionError,
				validate_report_access,
				"Revenue Summary",
				user="frontdesk@example.com",
			)

	def test_normalize_report_filters_defaults_branch_for_branch_scoped_user(self):
		frappe_stub = SimpleNamespace(
			_dict=lambda value=None: frappe._dict(value or {}),
			defaults=SimpleNamespace(get_user_default=lambda key: None),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.PermissionError)()),
			PermissionError=frappe.PermissionError,
		)

		with (
			patch("vetedge.services.report_visibility.frappe", frappe_stub),
			patch("vetedge.services.report_visibility.is_portal_owner_user", return_value=False),
			patch("vetedge.services.report_visibility.get_user_roles", return_value={"Branch Manager"}),
			patch("vetedge.services.report_visibility.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.report_visibility.get_assigned_branches", return_value=["Main Branch"]),
		):
			filters = normalize_report_filters(
				"Branch Performance Summary",
				{},
				user="manager@example.com",
			)

		self.assertEqual(filters.branch, "Main Branch")

	def test_hospitalisation_dashboard_allows_clinical_roles_and_defaults_branch(self):
		frappe_stub = SimpleNamespace(
			_dict=lambda value=None: frappe._dict(value or {}),
			defaults=SimpleNamespace(get_user_default=lambda key: None),
			throw=lambda message, exc=None: (_ for _ in ()).throw((exc or frappe.PermissionError)()),
			PermissionError=frappe.PermissionError,
		)

		with (
			patch("vetedge.services.report_visibility.frappe", frappe_stub),
			patch("vetedge.services.report_visibility.is_portal_owner_user", return_value=False),
			patch("vetedge.services.report_visibility.get_user_roles", return_value={"VetEdge Doctor"}),
			patch("vetedge.services.report_visibility.user_has_global_branch_access", return_value=False),
			patch("vetedge.services.report_visibility.get_assigned_branches", return_value=["Main Branch"]),
		):
			validate_dashboard_access("hospitalisation", user="doctor@example.com")
			filters = normalize_dashboard_filters(
				"hospitalisation",
				{},
				user="doctor@example.com",
			)

		self.assertEqual(filters.branch, "Main Branch")
