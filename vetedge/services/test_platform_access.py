# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import frappe
from vetedge.services.platform_access import require_vetedge_platform_access
from vetedge.coreedge_adapter import is_coreedge_available

class TestPlatformAccess(unittest.TestCase):
	def setUp(self):
		self.orig_conf = dict(frappe.conf)
		# Start with a clean slate for edge platform configuration
		for key in ("coreedge_required", "edge_platform_mode", "edge_platform_product"):
			if key in frappe.conf:
				del frappe.conf[key]

	def tearDown(self):
		frappe.conf.clear()
		frappe.conf.update(self.orig_conf)

	def test_standalone_mode_is_noop(self):
		# Standalone mode must be a no-op even if CoreEdge is missing
		frappe.conf.edge_platform_mode = "standalone"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			# Should not raise any error
			require_vetedge_platform_access(action="test_action")

	def test_shared_hosted_fails_closed_when_coreedge_missing(self):
		# shared_hosted fails closed when CoreEdge is missing
		frappe.conf.edge_platform_mode = "shared_hosted"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			with self.assertRaises(frappe.PermissionError) as context:
				require_vetedge_platform_access(action="test_action")
			self.assertIn("CoreEdge Platform is required but not installed or available.", str(context.exception))

	def test_white_label_fails_closed_when_coreedge_missing(self):
		# white_label fails closed when CoreEdge is missing
		frappe.conf.edge_platform_mode = "white_label"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			with self.assertRaises(frappe.PermissionError) as context:
				require_vetedge_platform_access(action="test_action")
			self.assertIn("CoreEdge Platform is required but not installed or available.", str(context.exception))

	def test_coreedge_active_allows_protected_actions(self):
		# When CoreEdge is active/available and active product app allows, it should proceed
		frappe.conf.edge_platform_mode = "shared_hosted"
		mock_require = MagicMock()
		
		# Remove actual coreedge modules from cache to force mock lookup
		old_modules = {}
		for k in list(sys.modules.keys()):
			if k.startswith("coreedge"):
				old_modules[k] = sys.modules[k]
				del sys.modules[k]

		mock_access = MagicMock()
		mock_access.require_product_access = mock_require
		sys.modules["coreedge"] = MagicMock()
		sys.modules["coreedge.adapters"] = MagicMock()
		sys.modules["coreedge.adapters.access"] = mock_access

		try:
			with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
				require_vetedge_platform_access(action="test_action", reference_doctype="Veterinary Patient", reference_name="VP-001")
				self.assertTrue(mock_require.called)
		finally:
			# Restore sys.modules
			for k in list(sys.modules.keys()):
				if k.startswith("coreedge"):
					del sys.modules[k]
			sys.modules.update(old_modules)

	def test_coreedge_blocked_blocks_protected_actions(self):
		# When CoreEdge is active but blocks (raises PermissionError), the action must be blocked
		frappe.conf.edge_platform_mode = "shared_hosted"
		mock_require = MagicMock()
		mock_require.side_effect = frappe.PermissionError("Suspended")
		
		old_modules = {}
		for k in list(sys.modules.keys()):
			if k.startswith("coreedge"):
				old_modules[k] = sys.modules[k]
				del sys.modules[k]

		mock_access = MagicMock()
		mock_access.require_product_access = mock_require
		sys.modules["coreedge"] = MagicMock()
		sys.modules["coreedge.adapters"] = MagicMock()
		sys.modules["coreedge.adapters.access"] = mock_access

		try:
			with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=True):
				with self.assertRaises(frappe.PermissionError):
					require_vetedge_platform_access(action="test_action")
		finally:
			for k in list(sys.modules.keys()):
				if k.startswith("coreedge"):
					del sys.modules[k]
			sys.modules.update(old_modules)

	def test_service_files_do_not_import_coreedge_directly(self):
		# None of the service files under vetedge/services/ should import from coreedge directly.
		# They must go through the adapter or platform_access wrapper.
		services_dir = os.path.dirname(os.path.abspath(__file__))
		for filename in os.listdir(services_dir):
			if filename.endswith(".py") and filename not in ("test_platform_access.py", "platform_access.py"):
				filepath = os.path.join(services_dir, filename)
				with open(filepath, "r", encoding="utf-8") as f:
					content = f.read()
					self.assertNotIn("import coreedge", content, f"Direct coreedge import found in {filename}")
					self.assertNotIn("from coreedge", content, f"Direct coreedge import found in {filename}")

	def test_no_user_facing_saas_wording(self):
		# Platform gate errors must use neutral wording (no "SaaS", "subscription", etc.)
		frappe.conf.edge_platform_mode = "shared_hosted"
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			try:
				require_vetedge_platform_access(action="test_action")
			except frappe.PermissionError as e:
				msg = str(e).lower()
				self.assertNotIn("saas", msg)
				self.assertNotIn("subscription", msg)
				self.assertNotIn("billing", msg)

	def test_gated_workflows_trigger_checks(self):
		# Mock platform access to raise PermissionError, assert gated workflows fail
		with patch("vetedge.services.platform_access.require_vetedge_platform_access") as mock_gate:
			mock_gate.side_effect = frappe.PermissionError("Blocked by gate")
			
			# Test create_consultation_from_appointment
			from vetedge.services.appointment_flow import create_consultation_from_appointment
			
			# Patch other prerequisites to isolate the gate
			with (
				patch("vetedge.services.appointment_flow.require_internal_user"),
				patch("vetedge.services.appointment_flow.ensure_appointments_enabled"),
				patch("vetedge.services.appointment_flow.frappe.get_doc")
			):
				with self.assertRaises(frappe.PermissionError) as ctx:
					create_consultation_from_appointment("APPT-001")
				self.assertEqual("Blocked by gate", str(ctx.exception))
