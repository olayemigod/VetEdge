# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import sys
import frappe
from frappe import _

# Gated functions to test
from vetedge.services.appointment_flow import create_follow_up_from_consultation, create_consultation_from_appointment
from vetedge.services.consultation_flow import transition_consultation_status
from vetedge.services.billing_modal import (
	create_invoice_from_modal,
	create_or_update_modal_invoice,
	create_payment_from_modal,
	submit_modal_invoice,
	record_modal_invoice_payment,
	get_billing_modal_state
)
from vetedge.services.lab import create_lab_order_from_consultation, create_standalone_lab_order, create_lab_order_invoice
from vetedge.services.vaccination import create_vaccination_from_consultation, administer_vaccination, create_or_update_vaccination_invoice
from vetedge.services.hospitalisation import create_hospitalisation_from_consultation, sync_hospitalisation_charges_to_invoice, admit_hospitalisation, discharge_hospitalisation
from vetedge.services.grooming import create_grooming_session_from_appointment, create_or_update_grooming_invoice
from vetedge.services.boarding import reserve_boarding_booking, check_in_boarding_booking, check_out_boarding_booking, create_boarding_invoice, cancel_boarding_booking
from vetedge.services.appointment_flow import transition_appointment_status


class TestPlatformV21ApiSimulation(unittest.TestCase):
	def setUp(self):
		self.orig_conf = dict(frappe.conf)
		# Clean slate for platform site config
		for key in ("coreedge_required", "edge_platform_mode", "edge_platform_product"):
			if key in frappe.conf:
				del frappe.conf[key]

		# Setup prerequisite patches to isolate the access gate
		self.setup_prerequisites_patches()

	def tearDown(self):
		frappe.conf.clear()
		frappe.conf.update(self.orig_conf)
		self.teardown_prerequisites_patches()

	def setup_prerequisites_patches(self):
		# Create persistent patches that bypass basic logic so we only test gates
		self.patches = [
			patch("vetedge.services.appointment_flow.require_internal_user"),
			patch("vetedge.services.appointment_flow.ensure_appointments_enabled"),
			patch("vetedge.services.appointment_flow.can_access_consultation"),
			patch("vetedge.services.appointment_flow.frappe.get_doc"),
			patch("vetedge.services.appointment_flow.normalize_consultation_links"),
			patch("vetedge.services.appointment_flow.validate_start_consultation_from_appointment"),
			patch("vetedge.services.appointment_flow.assert_consultation_can_proceed"),

			patch("vetedge.services.consultation_flow.require_internal_user"),
			patch("vetedge.services.consultation_flow.ensure_consultations_enabled"),
			patch("vetedge.services.consultation_flow.frappe.get_doc"),
			patch("vetedge.services.consultation_flow.can_access_consultation"),

			patch("vetedge.services.billing_modal.require_internal_user"),
			patch("vetedge.services.billing_modal.get_billing_source_config"),
			patch("vetedge.services.billing_modal.frappe.get_doc"),
			patch("vetedge.services.billing_modal.assert_can_act_on_source"),
			patch("vetedge.services.billing_modal.assert_can_read_source"),

			patch("vetedge.services.lab.require_internal_user"),
			patch("vetedge.services.lab.can_access_consultation"),
			patch("vetedge.services.lab.frappe.get_doc"),
			patch("vetedge.services.lab.can_request_lab_tests"),
			patch("vetedge.services.lab.can_access_lab_order"),

			patch("vetedge.services.vaccination.require_internal_user"),
			patch("vetedge.services.vaccination.ensure_vaccination_enabled"),
			patch("vetedge.services.vaccination.frappe.get_doc"),
			patch("vetedge.services.vaccination.can_access_consultation"),
			patch("vetedge.services.vaccination.require_vaccination_branch_access"),
			patch("vetedge.services.vaccination.can_administer_vaccine"),

			patch("vetedge.services.hospitalisation.require_internal_user"),
			patch("vetedge.services.hospitalisation.assert_hospitalisation_enabled"),
			patch("vetedge.services.hospitalisation.frappe.get_doc"),
			patch("vetedge.services.hospitalisation.normalize_discharge_details"),
			patch("vetedge.services.hospitalisation.build_hospitalisation_discharge_readiness"),

			patch("vetedge.services.grooming.require_internal_user"),
			patch("vetedge.services.grooming.ensure_grooming_enabled"),
			patch("vetedge.services.grooming.frappe.get_doc"),
			patch("vetedge.services.grooming.can_create_grooming_session"),
			patch("vetedge.services.grooming.can_manage_grooming_billing"),

			patch("vetedge.services.boarding.require_internal_user"),
			patch("vetedge.services.boarding.ensure_boarding_enabled"),
			patch("vetedge.services.boarding.frappe.get_doc"),
		]
		for p in self.patches:
			p.start()

	def teardown_prerequisites_patches(self):
		for p in reversed(self.patches):
			p.stop()

	def _get_gated_actions_map(self):
		# Maps docname/args to whitelisted actions for easy testing
		return {
			"create_follow_up_from_consultation": lambda: create_follow_up_from_consultation("VCON-001", "2026-06-23 09:00:00"),
			"create_consultation_from_appointment": lambda: create_consultation_from_appointment("APPT-001"),
			"transition_consultation_status": lambda: transition_consultation_status("VCON-001", "Completed"),
			"create_invoice_from_modal": lambda: create_invoice_from_modal("Veterinary Consultation", "VCON-001"),
			"create_or_update_modal_invoice": lambda: create_or_update_modal_invoice("Veterinary Consultation", "VCON-001"),
			"create_payment_from_modal": lambda: create_payment_from_modal("Veterinary Consultation", "VCON-001"),
			"submit_modal_invoice": lambda: submit_modal_invoice("Veterinary Consultation", "VCON-001"),
			"record_modal_invoice_payment": lambda: record_modal_invoice_payment("Veterinary Consultation", "VCON-001"),
			"create_lab_order_from_consultation": lambda: create_lab_order_from_consultation("VCON-001", lab_tests="[]"),
			"create_standalone_lab_order": lambda: create_standalone_lab_order("VP-001", lab_tests="[]"),
			"create_lab_order_invoice": lambda: create_lab_order_invoice("LAB-001"),
			"create_vaccination_from_consultation": lambda: create_vaccination_from_consultation("VCON-001", vaccine="V-001"),
			"administer_vaccination": lambda: administer_vaccination("VAC-001"),
			"create_or_update_vaccination_invoice": lambda: create_or_update_vaccination_invoice("VAC-001"),
			"create_hospitalisation_from_consultation": lambda: create_hospitalisation_from_consultation("VCON-001"),
			"sync_hospitalisation_charges_to_invoice": lambda: sync_hospitalisation_charges_to_invoice("VHOS-001"),
			"admit_hospitalisation": lambda: admit_hospitalisation("VHOS-001"),
			"discharge_hospitalisation": lambda: discharge_hospitalisation("VHOS-001", discharge_summary="Summary"),
			"create_grooming_session_from_appointment": lambda: create_grooming_session_from_appointment("APPT-001"),
			"create_or_update_grooming_invoice": lambda: create_or_update_grooming_invoice("GROOM-001"),
			"reserve_boarding_booking": lambda: reserve_boarding_booking("BOARD-001"),
			"check_in_boarding_booking": lambda: check_in_boarding_booking("BOARD-001"),
			"check_out_boarding_booking": lambda: check_out_boarding_booking("BOARD-001"),
			"create_boarding_invoice": lambda: create_boarding_invoice("BOARD-001")
		}

	def test_standalone_mode_gated_actions_allowed_without_coreedge(self):
		# Standalone mode should proceed without throwing platform gate errors
		frappe.conf.edge_platform_mode = "standalone"
		
		# Mock is_coreedge_available = False (CoreEdge not installed)
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			for action_name, action_func in self._get_gated_actions_map().items():
				with self.subTest(action=action_name):
					try:
						action_func()
					except frappe.PermissionError as e:
						# PermissionError is fine if it comes from the business logic mocks,
						# but NOT from the platform gate "CoreEdge Platform is required..."
						self.assertNotIn("CoreEdge Platform is required", str(e))
					except Exception:
						# Other business exceptions/KeyErrors due to mocked environments are allowed
						pass

	def test_shared_hosted_mode_fails_closed_when_coreedge_missing(self):
		# shared_hosted fails closed when CoreEdge is missing
		frappe.conf.edge_platform_mode = "shared_hosted"
		
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			for action_name, action_func in self._get_gated_actions_map().items():
				with self.subTest(action=action_name):
					with self.assertRaises(frappe.PermissionError) as context:
						action_func()
					self.assertIn("CoreEdge Platform is required but not installed or available.", str(context.exception))
					# Confirm no SaaS-specific words
					self.assertNotIn("saas", str(context.exception).lower())
					self.assertNotIn("subscription", str(context.exception).lower())

	def test_white_label_mode_fails_closed_when_coreedge_missing(self):
		# white_label fails closed when CoreEdge is missing
		frappe.conf.edge_platform_mode = "white_label"
		
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			for action_name, action_func in self._get_gated_actions_map().items():
				with self.subTest(action=action_name):
					with self.assertRaises(frappe.PermissionError) as context:
						action_func()
					self.assertIn("CoreEdge Platform is required but not installed or available.", str(context.exception))
					# Confirm no SaaS-specific words
					self.assertNotIn("saas", str(context.exception).lower())

	def test_coreedge_active_product_allows_protected_actions(self):
		# CoreEdge active allows protected actions to proceed past the gate
		frappe.conf.edge_platform_mode = "shared_hosted"
		mock_require = MagicMock()

		# Force inline imports inside adapter to yield mock
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
				for action_name, action_func in self._get_gated_actions_map().items():
					with self.subTest(action=action_name):
						mock_require.reset_mock()
						try:
							action_func()
						except Exception:
							pass
						self.assertTrue(mock_require.called, f"Gate not hit for {action_name}")
		finally:
			for k in list(sys.modules.keys()):
				if k.startswith("coreedge"):
					del sys.modules[k]
			sys.modules.update(old_modules)

	def test_coreedge_blocked_product_blocks_protected_actions(self):
		# CoreEdge suspended/expired/blocked blocks actions cleanly
		frappe.conf.edge_platform_mode = "shared_hosted"
		
		mock_require = MagicMock()
		mock_require.side_effect = frappe.PermissionError("Blocked by CoreEdge runtime policy")

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
				for action_name, action_func in self._get_gated_actions_map().items():
					with self.subTest(action=action_name):
						with self.assertRaises(frappe.PermissionError) as context:
							action_func()
						self.assertEqual("Blocked by CoreEdge runtime policy", str(context.exception))
		finally:
			for k in list(sys.modules.keys()):
				if k.startswith("coreedge"):
					del sys.modules[k]
			sys.modules.update(old_modules)

	def test_deferred_and_read_only_actions_remain_ungated(self):
		# Gating must NOT block read-only queries or deferred/cancellation actions
		frappe.conf.edge_platform_mode = "shared_hosted"
		
		# CoreEdge missing
		with patch("vetedge.coreedge_adapter.is_coreedge_available", return_value=False):
			# 1. Billing modal state read
			try:
				get_billing_modal_state("Veterinary Consultation", "VCON-001")
			except frappe.PermissionError as e:
				self.assertNotIn("CoreEdge Platform is required", str(e))
			except Exception:
				pass

			# 2. Gated transition_appointment_status (deferred)
			try:
				transition_appointment_status("APPT-001", "Cancelled")
			except frappe.PermissionError as e:
				self.assertNotIn("CoreEdge Platform is required", str(e))
			except Exception:
				pass

			# 3. Gated cancel_boarding_booking (deferred)
			try:
				cancel_boarding_booking("BOARD-001")
			except frappe.PermissionError as e:
				self.assertNotIn("CoreEdge Platform is required", str(e))
			except Exception:
				pass
