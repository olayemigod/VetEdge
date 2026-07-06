from __future__ import annotations

from pathlib import Path
from unittest import TestCase
from types import SimpleNamespace
from unittest.mock import Mock, patch

import frappe

from vetedge.services import billing_modal


class TestBillingModal(TestCase):
	def test_supported_billing_sources_are_registered(self):
		self.assertIn("Veterinary Consultation", billing_modal.BILLING_SOURCE_CONFIGS)
		self.assertIn("Veterinary Vaccination Record", billing_modal.BILLING_SOURCE_CONFIGS)
		self.assertIn("Pet Grooming Session", billing_modal.BILLING_SOURCE_CONFIGS)
		self.assertIn("Pet Boarding Booking", billing_modal.BILLING_SOURCE_CONFIGS)
		self.assertIn("Veterinary Lab Order", billing_modal.BILLING_SOURCE_CONFIGS)

	def test_consultation_modal_config_uses_existing_billing_services(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")

		self.assertEqual(config.invoice_link_field, "linked_invoice")
		self.assertEqual(config.create_invoice_method, "vetedge.services.billing.create_consultation_invoice")
		self.assertEqual(config.payment_method, "vetedge.services.billing.create_payment_entry_from_consultation")

	def test_submitted_invoice_blocks_duplicate_invoice_creation(self):
		doc = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
		)

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal.frappe, "get_doc", return_value=doc),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_invoice_summary", return_value={"name": "SINV-001", "docstatus": 1}),
			patch.object(billing_modal, "get_billing_modal_state", return_value={"invoice": {"name": "SINV-001"}}),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=False),
			patch.object(billing_modal.frappe, "get_attr") as get_attr,
		):
			result = billing_modal.create_invoice_from_modal("Veterinary Consultation", "VCON-001")

		self.assertFalse(result["created"])
		self.assertEqual(result["message"], "An invoice is already linked to this document.")
		self.assertNotIn(
			("vetedge.services.billing.create_consultation_invoice",),
			[call.args for call in get_attr.call_args_list],
		)

	def test_draft_invoice_allows_existing_service_to_update_invoice(self):
		doc = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
		)
		create_invoice = Mock(return_value={"invoice": "SINV-001", "created": False})

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal.frappe, "get_doc", return_value=doc),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_invoice_summary", return_value={"name": "SINV-001", "docstatus": 0}),
			patch.object(billing_modal, "get_billing_modal_state", return_value={"invoice": {"name": "SINV-001"}}),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=False),
			patch.object(billing_modal.frappe, "get_attr", return_value=create_invoice),
		):
			result = billing_modal.create_invoice_from_modal("Veterinary Consultation", "VCON-001")

		self.assertTrue(result["created"])
		create_invoice.assert_any_call(consultation="VCON-001")

	def test_consultation_gate_state_reports_unspecified_missing_invoice_block(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001")

		with (
			patch("vetedge.services.payment_gate.get_consultation_payment_gate", return_value="Full Payment Required"),
			patch("vetedge.services.payment_gate.is_billable_consultation", return_value=True),
		):
			state = billing_modal.get_consultation_payment_gate_state(doc, None)

		self.assertFalse(state["can_proceed"])
		self.assertEqual(state["message"], "A Sales Invoice must be generated before this consultation can proceed.")

	def test_available_actions_enable_payment_only_for_submitted_supported_invoice(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")
		actions = billing_modal.get_available_actions(
			config,
			{"docstatus": 1, "is_submitted": True, "outstanding_amount": 1000},
		)

		self.assertFalse(actions["can_create_invoice"])
		self.assertTrue(actions["can_record_payment"])
		self.assertTrue(actions["can_open_full_invoice"])
		self.assertFalse(actions["can_submit_invoice"])

	def test_available_actions_enable_submit_for_draft_invoice(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")
		actions = billing_modal.get_available_actions(config, {"docstatus": 0, "is_draft": True})

		self.assertTrue(actions["can_create_invoice"])
		self.assertTrue(actions["can_submit_invoice"])
		self.assertFalse(actions["can_record_payment"])

	def test_modal_session_actions_create_invoice_for_pending_charges_without_invoice(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")
		session = {"invoices": [], "charges": [{"billing_status": "Pending", "invoice": None}]}

		actions = billing_modal.get_available_actions(config, None, session)

		self.assertTrue(actions["can_create_or_update_invoice"])
		self.assertEqual(actions["invoice_action_label"], "Create Invoice")
		self.assertEqual(actions["pending_charge_count"], 1)
		self.assertFalse(actions["can_open_full_invoice"])

	def test_modal_session_actions_update_and_open_draft_invoice(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")
		session = {
			"current_draft_invoice": "SINV-DRAFT",
			"latest_invoice": "SINV-DRAFT",
			"invoices": [{"name": "SINV-DRAFT", "docstatus": 0}],
			"charges": [{"billing_status": "Draft Invoiced", "invoice": "SINV-DRAFT"}],
		}

		actions = billing_modal.get_available_actions(config, {"name": "SINV-DRAFT", "docstatus": 0, "is_draft": True}, session)

		self.assertTrue(actions["can_create_or_update_invoice"])
		self.assertEqual(actions["invoice_action_label"], "Update Draft Invoice")
		self.assertEqual(actions["open_invoice_label"], "Open Draft Invoice")
		self.assertEqual(actions["open_invoice_name"], "SINV-DRAFT")
		self.assertEqual(actions["pending_charge_count"], 0)

	def test_modal_session_actions_create_next_invoice_after_submitted_invoice_with_pending_charge(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")
		session = {
			"latest_invoice": "SINV-SUBMITTED",
			"invoices": [{"name": "SINV-SUBMITTED", "docstatus": 1}],
			"charges": [
				{"billing_status": "Submitted Invoiced", "invoice": "SINV-SUBMITTED"},
				{"billing_status": "Pending", "invoice": None},
			],
		}

		actions = billing_modal.get_available_actions(config, {"name": "SINV-SUBMITTED", "docstatus": 1, "is_submitted": True}, session)

		self.assertTrue(actions["can_create_or_update_invoice"])
		self.assertEqual(actions["invoice_action_label"], "Create Next Invoice")
		self.assertEqual(actions["open_invoice_label"], "Open Submitted Invoice")
		self.assertEqual(actions["latest_invoice_docstatus"], 1)
		self.assertEqual(actions["pending_charge_count"], 1)

	def test_modal_session_actions_create_new_invoice_after_cancelled_invoice_with_pending_charge(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")
		session = {
			"latest_invoice": "SINV-CANCELLED",
			"invoices": [{"name": "SINV-CANCELLED", "docstatus": 2}],
			"charges": [{"billing_status": "Pending", "invoice": None}],
		}

		actions = billing_modal.get_available_actions(config, {"name": "SINV-CANCELLED", "docstatus": 2}, session)

		self.assertTrue(actions["can_create_or_update_invoice"])
		self.assertEqual(actions["invoice_action_label"], "Create New Invoice")
		self.assertEqual(actions["open_invoice_label"], "Open Latest Invoice")
		self.assertEqual(actions["latest_invoice_docstatus"], 2)

	def test_modal_session_actions_do_not_offer_invoice_creation_without_pending_charges(self):
		config = billing_modal.get_billing_source_config("Veterinary Consultation")
		session = {
			"latest_invoice": "SINV-SUBMITTED",
			"invoices": [{"name": "SINV-SUBMITTED", "docstatus": 1}],
			"charges": [{"billing_status": "Submitted Invoiced", "invoice": "SINV-SUBMITTED"}],
		}

		actions = billing_modal.get_available_actions(config, {"name": "SINV-SUBMITTED", "docstatus": 1, "is_submitted": True}, session)

		self.assertFalse(actions["can_create_or_update_invoice"])
		self.assertEqual(actions["invoice_action_label"], "No pending uninvoiced charges.")
		self.assertEqual(actions["pending_charge_count"], 0)
		self.assertTrue(actions["can_open_full_invoice"])

	def test_all_shared_modal_sources_use_billing_core_action_state(self):
		session = {
			"latest_invoice": "SINV-SUBMITTED",
			"invoices": [{"name": "SINV-SUBMITTED", "docstatus": 1}],
			"charges": [{"billing_status": "Pending", "invoice": None}],
		}

		for source_doctype in (
			"Veterinary Consultation",
			"Veterinary Lab Order",
			"Veterinary Vaccination Record",
			"Veterinary Hospitalisation",
			"Pet Grooming Session",
			"Pet Boarding Booking",
			"Veterinary Patient",
		):
			with self.subTest(source_doctype=source_doctype):
				config = billing_modal.get_billing_source_config(source_doctype)
				actions = billing_modal.get_available_actions(
					config,
					{"name": "SINV-SUBMITTED", "docstatus": 1, "is_submitted": True},
					session,
				)
				self.assertTrue(actions["can_create_or_update_invoice"])
				self.assertEqual(actions["invoice_action_label"], "Create Next Invoice")
				self.assertEqual(actions["open_invoice_name"], "SINV-SUBMITTED")

	def test_billing_modal_js_consumes_billing_core_invoice_action_fields(self):
		js = get_app_file("vetedge/public/js/billing_modal.js").read_text()

		self.assertIn("actions.invoice_action_label", js)
		self.assertIn("actions.can_create_or_update_invoice", js)
		self.assertIn("vetedge.services.billing_modal.create_or_update_modal_invoice", js)
		self.assertIn("state?.actions?.open_invoice_name", js)
		self.assertNotIn("Open Full Invoice", js)

	def test_billing_modal_totals_use_session_ledger_and_keep_current_invoice_separate(self):
		invoice_summary = {
			"name": "SINV-DRAFT",
			"docstatus": 0,
			"status": "Draft",
			"payment_status": "Draft",
			"grand_total": 5000,
			"paid_amount": 0,
			"outstanding_amount": 5000,
			"currency": "NGN",
		}
		session_summary = {
			"name": "VBS-001",
			"total_invoiced": 107399,
			"total_paid": 25000,
			"outstanding_amount": 77399,
			"payment_status": "Partly Paid",
			"invoices": [
				{"name": "SINV-OLD", "docstatus": 1, "grand_total": 102399, "paid_amount": 25000, "outstanding_amount": 77399},
				{"name": "SINV-DRAFT", "docstatus": 0, "grand_total": 5000, "paid_amount": 0, "outstanding_amount": 5000},
				{"name": "SINV-CANCELLED", "docstatus": 2, "grand_total": 9999, "paid_amount": 0, "outstanding_amount": 9999},
			],
			"invoice_ledger": {"currency": "NGN", "payment_status": "Partly Paid"},
		}

		totals = billing_modal.get_billing_modal_totals(session_summary, invoice_summary)

		self.assertEqual(totals["total_amount"], 107399)
		self.assertEqual(totals["paid_amount"], 25000)
		self.assertEqual(totals["outstanding_amount"], 77399)
		self.assertEqual(totals["billing_session_outstanding"], 77399)
		self.assertEqual(totals["linked_invoice_count"], 2)
		self.assertEqual(totals["linked_invoices"], ["SINV-OLD", "SINV-DRAFT"])
		self.assertEqual(totals["current_invoice_name"], "SINV-DRAFT")
		self.assertEqual(totals["current_invoice_outstanding"], 5000)

	def test_billing_modal_state_uses_session_totals_without_syncing_charges(self):
		source = frappe._dict(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			status="Under Care",
			patient="VP-001",
			customer="CUST-001",
			sales_invoice="SINV-DRAFT",
		)
		invoice_summary = {
			"name": "SINV-DRAFT",
			"docstatus": 0,
			"is_draft": True,
			"grand_total": 5000,
			"paid_amount": 0,
			"outstanding_amount": 5000,
			"currency": "NGN",
		}
		session_summary = {
			"name": "VBS-001",
			"current_draft_invoice": "SINV-DRAFT",
			"latest_invoice": "SINV-DRAFT",
			"total_invoiced": 107399,
			"total_paid": 25000,
			"outstanding_amount": 77399,
			"payment_status": "Partly Paid",
			"payment_gate": {"gate": "Partial Payment Gate", "can_proceed": True, "message": "Session has partial payment and outstanding balance."},
			"invoices": [
				{"name": "SINV-OLD", "docstatus": 1, "grand_total": 102399, "paid_amount": 25000, "outstanding_amount": 77399},
				{"name": "SINV-DRAFT", "docstatus": 0, "grand_total": 5000, "paid_amount": 0, "outstanding_amount": 5000},
			],
			"charges": [],
			"invoice_ledger": {"currency": "NGN", "payment_status": "Partly Paid"},
		}

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal.frappe, "get_doc", return_value=source),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_linked_invoice_name", return_value="SINV-DRAFT"),
			patch.object(billing_modal, "get_invoice_summary", return_value=invoice_summary),
			patch.object(billing_modal, "get_payment_modes", return_value=[]),
			patch("vetedge.services.billing_core.resolve_billing_session", return_value=frappe._dict(name="VBS-001")),
			patch("vetedge.services.billing_core.get_billing_session_summary", return_value=session_summary),
			patch("vetedge.services.billing_core.sync_source_charge_payloads_to_billing_session", side_effect=AssertionError("summary must not sync charges")),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=True),
			patch.object(billing_modal, "get_billing_group_history_for_modal", return_value=[]),
			patch.object(billing_modal, "get_billing_group_payment_gate_for_modal", return_value=None),
		):
			state = billing_modal.get_billing_modal_state("Veterinary Hospitalisation", "VHOS-001")

		self.assertEqual(state["billing_session_total"], 107399)
		self.assertEqual(state["outstanding_amount"], 77399)
		self.assertEqual(state["current_invoice_outstanding"], 5000)
		self.assertEqual(state["payment_gate"]["message"], "Session has partial payment and outstanding balance.")

	def test_consultation_modal_state_syncs_plan_rows_before_action_summary(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			status="Open",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
			linked_invoice="SINV-SUBMITTED",
		)
		invoice_summary = {
			"name": "SINV-SUBMITTED",
			"docstatus": 1,
			"is_submitted": True,
			"grand_total": 5000,
			"paid_amount": 5000,
			"outstanding_amount": 0,
			"currency": "NGN",
		}
		session = frappe._dict(name="VBS-001")
		session_summary = {
			"name": "VBS-001",
			"current_draft_invoice": None,
			"latest_invoice": "SINV-SUBMITTED",
			"total_invoiced": 5000,
			"total_paid": 5000,
			"outstanding_amount": 0,
			"payment_status": "Paid",
			"invoices": [{"name": "SINV-SUBMITTED", "docstatus": 1, "grand_total": 5000, "paid_amount": 5000, "outstanding_amount": 0}],
			"charges": [
				{"billing_status": "Submitted Invoiced", "invoice": "SINV-SUBMITTED"},
				{
					"billing_status": "Pending",
					"invoice": None,
					"source_row_id": "consultation-plan::manual::row-new",
					"item_code": "Dog_Food",
				},
			],
			"invoice_ledger": {"currency": "NGN", "payment_status": "Paid"},
		}

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal.frappe, "get_doc", return_value=source),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_linked_invoice_name", return_value="SINV-SUBMITTED"),
			patch.object(billing_modal, "get_invoice_summary", return_value=invoice_summary),
			patch.object(billing_modal, "get_payment_modes", return_value=[]),
			patch("vetedge.services.billing_core.sync_source_charge_payloads_to_billing_session", return_value=session) as sync_mock,
			patch("vetedge.services.billing_core.get_billing_session_summary", return_value=session_summary),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=True),
			patch.object(billing_modal, "get_billing_group_history_for_modal", return_value=[]),
			patch.object(billing_modal, "get_billing_group_payment_gate_for_modal", return_value=None),
		):
			state = billing_modal.get_billing_modal_state("Veterinary Consultation", "VCON-001")

		sync_mock.assert_called_once_with("Veterinary Consultation", "VCON-001")
		self.assertTrue(state["can_create_or_update_invoice"])
		self.assertEqual(state["invoice_action_label"], "Create Next Invoice")
		self.assertEqual(state["pending_charge_count"], 1)

	def test_consultation_modal_state_does_not_show_closed_satisfied_session_as_active(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			status="Open",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
			linked_invoice="SINV-SUBMITTED",
		)
		invoice_summary = {
			"name": "SINV-SUBMITTED",
			"docstatus": 1,
			"is_submitted": True,
			"grand_total": 5000,
			"paid_amount": 5000,
			"outstanding_amount": 0,
			"currency": "NGN",
		}
		closed_session = frappe._dict(name="VBS-CLOSED", status="Closed")

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal.frappe, "get_doc", return_value=source),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_linked_invoice_name", return_value="SINV-SUBMITTED"),
			patch.object(billing_modal, "get_invoice_summary", return_value=invoice_summary),
			patch.object(billing_modal, "get_payment_modes", return_value=[]),
			patch("vetedge.services.billing_core.resolve_billing_session", return_value=closed_session),
			patch("vetedge.services.billing_core.closed_billing_session_covers_current_source_payloads", return_value=True),
			patch("vetedge.services.billing_core.sync_source_charge_payloads_to_billing_session", side_effect=AssertionError("closed satisfied sessions must not sync")),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=True),
			patch.object(
				billing_modal,
				"get_billing_group_history_for_modal",
				return_value=[
					{
						"name": "SINV-SUBMITTED",
						"invoice": "SINV-SUBMITTED",
						"docstatus": 1,
						"grand_total": 5000,
						"paid_amount": 5000,
						"outstanding_amount": 0,
						"payment_state": "Paid",
					}
				],
			),
			patch.object(billing_modal, "get_billing_group_payment_gate_for_modal", return_value={"can_proceed": True, "message": "Payment gate passed."}),
		):
			state = billing_modal.get_billing_modal_state("Veterinary Consultation", "VCON-001")

		self.assertIsNone(state["billing_session"])
		self.assertEqual(state["invoice"]["name"], "SINV-SUBMITTED")
		self.assertFalse(state["can_create_or_update_invoice"])
		self.assertEqual(state["open_invoice_name"], "SINV-SUBMITTED")

	def test_billing_modal_totals_use_billing_group_history_for_multiple_invoices(self):
		invoice_summary = {"name": "ACC-SINV-2026-00128", "docstatus": 0, "grand_total": 25000, "paid_amount": 0, "outstanding_amount": 25000}
		session_summary = {"name": "VBS-ACTIVE", "total_invoiced": 25000, "total_paid": 0, "outstanding_amount": 25000, "payment_status": "Draft Invoice Pending"}
		history = [
			{"name": "ACC-SINV-2026-00127", "docstatus": 1, "grand_total": 100000, "paid_amount": 100000, "outstanding_amount": 0, "payment_state": "Paid"},
			{"name": "ACC-SINV-2026-00128", "docstatus": 0, "grand_total": 25000, "paid_amount": 0, "outstanding_amount": 25000, "payment_state": "Draft"},
		]

		totals = billing_modal.get_billing_modal_totals(session_summary, invoice_summary, history)

		self.assertEqual(totals["linked_invoices"], ["ACC-SINV-2026-00127", "ACC-SINV-2026-00128"])
		self.assertEqual(totals["linked_invoice_count"], 2)
		self.assertEqual(totals["total_amount"], 125000)
		self.assertEqual(totals["paid_amount"], 100000)
		self.assertEqual(totals["payment_status"], "Partly Paid")
		self.assertEqual(totals["current_invoice_name"], "ACC-SINV-2026-00128")

	def test_billing_modal_state_separates_active_session_from_invoice_history(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-2026-00069",
			status="Open",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
			linked_invoice="ACC-SINV-2026-00128",
		)
		invoice_summary = {"name": "ACC-SINV-2026-00128", "docstatus": 0, "is_draft": True, "grand_total": 25000, "paid_amount": 0, "outstanding_amount": 25000}
		session_summary = {
			"name": "VBS-ACTIVE",
			"current_draft_invoice": "ACC-SINV-2026-00128",
			"latest_invoice": "ACC-SINV-2026-00128",
			"invoices": [{"name": "ACC-SINV-2026-00128", "docstatus": 0, "grand_total": 25000, "paid_amount": 0, "outstanding_amount": 25000}],
			"charges": [],
		}
		history = [
			{"name": "ACC-SINV-2026-00127", "invoice": "ACC-SINV-2026-00127", "docstatus": 1, "grand_total": 100000, "paid_amount": 100000, "outstanding_amount": 0, "payment_state": "Paid", "is_history_invoice": True},
			{"name": "ACC-SINV-2026-00128", "invoice": "ACC-SINV-2026-00128", "docstatus": 0, "grand_total": 25000, "paid_amount": 0, "outstanding_amount": 25000, "payment_state": "Draft", "is_active_session_invoice": True},
		]

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal.frappe, "get_doc", return_value=source),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_linked_invoice_name", return_value="ACC-SINV-2026-00128"),
			patch.object(billing_modal, "get_invoice_summary", return_value=invoice_summary),
			patch.object(billing_modal, "get_payment_modes", return_value=[]),
			patch.object(billing_modal, "get_billing_session_summary_for_source", return_value=session_summary),
			patch.object(billing_modal, "get_billing_group_history_for_modal", return_value=history),
			patch.object(billing_modal, "get_billing_group_payment_gate_for_modal", return_value={"gate": "Partial Payment Gate", "can_proceed": True, "message": "Payment gate passed."}),
		):
			state = billing_modal.get_billing_modal_state("Veterinary Consultation", "VCON-2026-00069")

		self.assertEqual(state["billing_session"]["name"], "VBS-ACTIVE")
		self.assertEqual([row["name"] for row in state["invoice_history"]], ["ACC-SINV-2026-00127", "ACC-SINV-2026-00128"])
		self.assertEqual(state["linked_invoices"], ["ACC-SINV-2026-00127", "ACC-SINV-2026-00128"])
		self.assertTrue(state["payment_gate"]["can_proceed"])

	def test_billing_modal_state_separates_patient_outstanding_context(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-CURRENT",
			status="Open",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
		)
		history = [
			{"name": "ACC-SINV-CURRENT", "invoice": "ACC-SINV-CURRENT", "docstatus": 1, "grand_total": 10000, "paid_amount": 10000, "outstanding_amount": 0, "payment_state": "Paid"}
		]
		outstanding = [
			{"name": "ACC-SINV-OLD", "invoice": "ACC-SINV-OLD", "docstatus": 0, "grand_total": 7000, "paid_amount": 0, "outstanding_amount": 7000, "payment_state": "Draft", "informational_only": True}
		]

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal.frappe, "get_doc", return_value=source),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_linked_invoice_name", return_value=None),
			patch.object(billing_modal, "get_invoice_summary", return_value=None),
			patch.object(billing_modal, "get_payment_modes", return_value=[]),
			patch.object(billing_modal, "get_billing_session_summary_for_source", return_value=None),
			patch.object(billing_modal, "get_billing_group_history_for_modal", return_value=history),
			patch.object(billing_modal, "get_patient_outstanding_context_for_modal", return_value=outstanding),
			patch.object(billing_modal, "get_billing_group_payment_gate_for_modal", return_value={"gate": "Partial Payment Gate", "can_proceed": True, "message": "Payment gate passed."}),
		):
			state = billing_modal.get_billing_modal_state("Veterinary Consultation", "VCON-CURRENT")

		self.assertEqual([row["name"] for row in state["invoice_history"]], ["ACC-SINV-CURRENT"])
		self.assertEqual([row["name"] for row in state["patient_outstanding_context"]], ["ACC-SINV-OLD"])
		self.assertEqual(state["linked_invoice_count"], 1)
		self.assertEqual(state["linked_invoices"], ["ACC-SINV-CURRENT"])

	def test_billing_modal_js_renders_session_payment_summary(self):
		js = get_app_file("vetedge/public/js/billing_modal.js").read_text()

		self.assertIn("Billing Group Total", js)
		self.assertIn("Billing Group Payment Status", js)
		self.assertIn("Current Billing Cycle Status", js)
		self.assertIn("Other Outstanding Invoices for this Patient", js)
		self.assertIn("not part of this consultation billing group", js)
		self.assertIn("state.outstanding_amount", js)
		self.assertIn("currentInvoicePaymentBlock", js)
		self.assertIn("Current Draft Invoice", js)
		self.assertIn("pay-ledger-invoice", js)
		self.assertIn("selectedInvoice", js)

	def test_billable_source_forms_open_shared_billing_modal(self):
		for relative_path in (
			"vetedge/veterinary/doctype/veterinary_consultation/veterinary_consultation.js",
			"vetedge/veterinary/doctype/veterinary_lab_order/veterinary_lab_order.js",
			"vetedge/veterinary/doctype/veterinary_vaccination_record/veterinary_vaccination_record.js",
			"vetedge/veterinary/doctype/veterinary_hospitalisation/veterinary_hospitalisation.js",
			"vetedge/veterinary/doctype/pet_grooming_session/pet_grooming_session.js",
			"vetedge/veterinary/doctype/pet_boarding_booking/pet_boarding_booking.js",
			"vetedge/veterinary/doctype/veterinary_patient/veterinary_patient.js",
		):
			with self.subTest(relative_path=relative_path):
				js = get_app_file(relative_path).read_text()
				self.assertIn("vetedgeBillingModal", js)
				self.assertIn("window.vetedgeBillingModal.open(frm)", js)

	def test_consultation_billing_modal_saves_dirty_plan_rows_first(self):
		js = get_app_file("vetedge/veterinary/doctype/veterinary_consultation/veterinary_consultation.js").read_text()

		self.assertIn('frm.add_custom_button(__("Billing / Payment"), async () => {', js)
		self.assertLess(js.index("await frm.save();"), js.index("window.vetedgeBillingModal.open(frm)"))

	def test_completed_consultation_keeps_history_actions_visible(self):
		js = get_app_file("vetedge/veterinary/doctype/veterinary_consultation/veterinary_consultation.js").read_text()

		billing_fn = js.split("function add_billing_actions(frm) {", 1)[1].split(
			"function add_lab_actions(frm) {", 1
		)[0]
		lab_fn = js.split("function add_lab_actions(frm) {", 1)[1].split(
			"function show_consultation_lab_orders_dialog", 1
		)[0]
		vaccination_fn = js.split("function add_vaccination_actions(frm) {", 1)[1].split(
			"function show_vaccination_dialog", 1
		)[0]

		self.assertIn('frm.doc.status !== "Cancelled"', billing_fn)
		self.assertIn('frm.doc.status === "Cancelled"', lab_fn)
		self.assertIn('frm.add_custom_button(__("View Lab Orders")', lab_fn)
		self.assertLess(lab_fn.index('frm.doc.status === "Cancelled"'), lab_fn.index('frm.add_custom_button(__("View Lab Orders")'))
		self.assertIn("if (!consultationScopeIsLocked(frm))", vaccination_fn)
		self.assertIn('frm.add_custom_button(__("View Vaccinations")', vaccination_fn)
		self.assertLess(vaccination_fn.index("if (!consultationScopeIsLocked(frm))"), vaccination_fn.index('frm.add_custom_button(__("View Vaccinations")'))

	def test_submit_modal_invoice_submits_draft_invoice(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=0)

		with (
			modal_action_context(source, invoice),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=True),
			patch.object(billing_modal, "source_supports_billing_session", return_value=True),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001"}) as sync_mock,
		):
			result = billing_modal.submit_modal_invoice("Veterinary Consultation", "VCON-001")

		self.assertEqual(result["invoice"], "SINV-001")
		invoice.submit.assert_called_once()
		sync_mock.assert_called_once_with("Veterinary Consultation", "VCON-001")

	def test_create_or_update_modal_invoice_returns_open_invoice_name_from_session_sync(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-SUBMITTED",
			service_branch="Main",
		)
		invoice = make_invoice(name="SINV-SUBMITTED", docstatus=1, outstanding_amount=0)
		state = {
			"invoice": {"name": "SINV-NEW"},
			"open_invoice_name": "SINV-NEW",
			"actions": {"open_invoice_name": "SINV-NEW"},
		}

		with (
			modal_action_context(source, invoice, state=state),
			patch.object(billing_modal, "get_invoice_summary", return_value={"name": "SINV-SUBMITTED", "docstatus": 1}),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=True),
			patch.object(billing_modal, "source_supports_billing_session", return_value=True),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-NEW"}) as sync_mock,
		):
			result = billing_modal.create_or_update_modal_invoice("Veterinary Consultation", "VCON-001")

		self.assertTrue(result["created"])
		self.assertEqual(result["invoice"], "SINV-NEW")
		self.assertEqual(result["open_invoice_name"], "SINV-NEW")
		sync_mock.assert_called_once_with("Veterinary Consultation", "VCON-001")

	def test_submit_modal_invoice_corrects_due_date_before_posting_date(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=0)
		invoice.posting_date = "2026-06-18"
		invoice.due_date = "2026-06-01"

		with (
			modal_action_context(source, invoice),
			patch("vetedge.services.billing_core.nowdate", return_value="2026-06-18"),
		):
			billing_modal.submit_modal_invoice("Veterinary Consultation", "VCON-001")

		self.assertEqual(invoice.set_posting_time, 1)
		self.assertEqual(invoice.posting_date, "2026-06-18")
		self.assertEqual(str(invoice.due_date), "2026-06-18")
		invoice.save.assert_called_once_with(ignore_permissions=True)
		invoice.submit.assert_called_once()

	def test_submit_modal_invoice_corrects_due_date_before_effective_submit_posting_date(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=0)
		invoice.posting_date = "2026-05-01"
		invoice.due_date = "2026-05-30"
		invoice.set_posting_time = 0

		with (
			modal_action_context(source, invoice),
			patch("vetedge.services.billing_core.nowdate", return_value="2026-06-18"),
		):
			billing_modal.submit_modal_invoice("Veterinary Consultation", "VCON-001")

		self.assertEqual(invoice.set_posting_time, 1)
		self.assertEqual(invoice.posting_date, "2026-06-18")
		self.assertEqual(str(invoice.due_date), "2026-06-18")
		invoice.save.assert_called_once_with(ignore_permissions=True)
		invoice.submit.assert_called_once()

	def test_submit_modal_invoice_preserves_due_date_after_posting_date(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=0)
		invoice.posting_date = "2026-06-18"
		invoice.due_date = "2026-07-18"

		with (
			modal_action_context(source, invoice),
			patch("vetedge.services.billing_core.nowdate", return_value="2026-06-18"),
		):
			billing_modal.submit_modal_invoice("Veterinary Consultation", "VCON-001")

		self.assertEqual(invoice.set_posting_time, 1)
		self.assertEqual(invoice.posting_date, "2026-06-18")
		self.assertEqual(invoice.due_date, "2026-07-18")
		invoice.save.assert_called_once_with(ignore_permissions=True)
		invoice.submit.assert_called_once()

	def test_submit_modal_invoice_preserves_valid_payment_terms_due_date_after_effective_posting_date(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=0)
		invoice.posting_date = "2026-05-01"
		invoice.due_date = "2026-07-18"
		invoice.set_posting_time = 0

		with (
			modal_action_context(source, invoice),
			patch("vetedge.services.billing_core.nowdate", return_value="2026-06-18"),
		):
			billing_modal.submit_modal_invoice("Veterinary Consultation", "VCON-001")

		self.assertEqual(invoice.set_posting_time, 1)
		self.assertEqual(invoice.posting_date, "2026-06-18")
		self.assertEqual(invoice.due_date, "2026-07-18")
		invoice.save.assert_called_once_with(ignore_permissions=True)
		invoice.submit.assert_called_once()

	def test_submit_modal_invoice_blocks_already_submitted_invoice(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=1)

		with modal_action_context(source, invoice):
			self.assertRaises(
				frappe.ValidationError,
				billing_modal.submit_modal_invoice,
				"Veterinary Consultation",
				"VCON-001",
			)

	def test_submit_modal_invoice_blocks_cancelled_invoice(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=2)

		with modal_action_context(source, invoice):
			self.assertRaises(
				frappe.ValidationError,
				billing_modal.submit_modal_invoice,
				"Veterinary Consultation",
				"VCON-001",
			)

	def test_record_modal_invoice_payment_submits_full_payment(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(outstanding_amount=1000)
		payment_entry = make_payment_entry()

		with (
			modal_action_context(source, invoice),
			patch("erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry", return_value=payment_entry),
		):
			result = billing_modal.record_modal_invoice_payment(
				"Veterinary Consultation",
				"VCON-001",
				amount=1000,
				mode_of_payment="Cash",
				reference_no="RCPT-001",
			)

		self.assertEqual(result["payment_entry"], "PE-001")
		self.assertEqual(payment_entry.paid_amount, 1000)
		self.assertEqual(payment_entry.references[0].allocated_amount, 1000)
		payment_entry.insert.assert_called_once()
		payment_entry.submit.assert_called_once()

	def test_record_modal_invoice_payment_allows_partial_payment_and_gate_remains_full_payment_blocked(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(outstanding_amount=1000)
		payment_entry = make_payment_entry()

		with (
			modal_action_context(source, invoice, state={"payment_gate": {"can_proceed": False}}),
			patch("erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry", return_value=payment_entry),
		):
			result = billing_modal.record_modal_invoice_payment("Veterinary Consultation", "VCON-001", amount=250)

		self.assertEqual(payment_entry.references[0].allocated_amount, 250)
		self.assertFalse(result["state"]["payment_gate"]["can_proceed"])

	def test_record_modal_invoice_payment_uses_selected_linked_invoice(self):
		source = frappe._dict(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			sales_invoice="SINV-CURRENT",
			service_branch="Main",
		)
		selected_invoice = make_invoice(name="SINV-OLD", outstanding_amount=400)
		payment_entry = make_payment_entry("SINV-OLD")
		state = {
			"billing_session": {"invoices": [{"name": "SINV-OLD", "docstatus": 1, "outstanding_amount": 400, "can_pay": True}]},
			"invoice": {"name": "SINV-CURRENT"},
		}

		with (
			modal_action_context(source, selected_invoice, state=state),
			patch.object(billing_modal, "get_billing_session_summary_for_source", return_value=state["billing_session"]),
			patch("erpnext.accounts.doctype.payment_entry.payment_entry.get_payment_entry", return_value=payment_entry) as get_payment_entry,
		):
			result = billing_modal.record_modal_invoice_payment("Veterinary Hospitalisation", "VHOS-001", invoice="SINV-OLD", amount=400)

		get_payment_entry.assert_called_once_with("Sales Invoice", "SINV-OLD")
		self.assertEqual(result["invoice"], "SINV-OLD")
		self.assertEqual(payment_entry.paid_amount, 400)
		self.assertEqual(payment_entry.references[0].allocated_amount, 400)
	def test_record_modal_invoice_payment_blocks_duplicate_reference(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(outstanding_amount=1000)

		with (
			modal_action_context(source, invoice),
			patch.object(billing_modal, "submitted_payment_exists", return_value=True),
		):
			self.assertRaises(
				frappe.ValidationError,
				billing_modal.record_modal_invoice_payment,
				"Veterinary Consultation",
				"VCON-001",
				reference_no="RCPT-001",
			)

	def test_branch_restricted_user_cannot_submit_invoice(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Restricted",
		)
		invoice = make_invoice(docstatus=0)

		with modal_action_context(source, invoice, branch_error=frappe.PermissionError):
			self.assertRaises(
				frappe.PermissionError,
				billing_modal.submit_modal_invoice,
				"Veterinary Consultation",
				"VCON-001",
			)

	def test_non_consultation_source_can_submit_invoice(self):
		source = frappe._dict(
			doctype="Pet Grooming Session",
			name="PGS-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=0)

		with modal_action_context(source, invoice):
			result = billing_modal.submit_modal_invoice("Pet Grooming Session", "PGS-001")

		self.assertEqual(result["invoice"], "SINV-001")
		invoice.submit.assert_called_once()


def make_invoice(name="SINV-001", docstatus=1, outstanding_amount=1000):
	return frappe._dict(
		doctype="Sales Invoice",
		name=name,
		docstatus=docstatus,
		status="Draft" if docstatus == 0 else "Unpaid",
		customer="CUST-001",
		branch="Main",
		posting_date="2026-06-18",
		due_date="2026-06-18",
		set_posting_time=1,
		grand_total=1000,
		paid_amount=0,
		outstanding_amount=outstanding_amount,
		currency="NGN",
		save=Mock(),
		submit=Mock(),
	)


def make_payment_entry(invoice_name="SINV-001"):
	return frappe._dict(
		doctype="Payment Entry",
		name="PE-001",
		paid_amount=0,
		received_amount=0,
		references=[frappe._dict(reference_doctype="Sales Invoice", reference_name=invoice_name, allocated_amount=0)],
		insert=Mock(),
		submit=Mock(),
	)


class modal_action_context:
	def __init__(self, source, invoice, state=None, branch_error=None):
		self.source = source
		self.invoice = invoice
		self.state = state or {"invoice": {"name": invoice.name}}
		self.branch_error = branch_error
		self.patches = []

	def __enter__(self):
		def get_doc(doctype, name):
			if doctype == self.source.doctype:
				return self.source
			if doctype == "Sales Invoice":
				return self.invoice
			raise AssertionError(f"Unexpected get_doc: {doctype} {name}")

		def exists(doctype, name=None):
			return doctype == "Sales Invoice" and name == self.invoice.name

		def throw(message, exc=None):
			raise (exc or frappe.ValidationError)(message)

		def branch_check(*args, **kwargs):
			if self.branch_error:
				raise self.branch_error()
			return True

		frappe_stub = SimpleNamespace(
			get_doc=get_doc,
			db=SimpleNamespace(exists=exists),
			session=SimpleNamespace(user="test@example.com"),
			has_permission=Mock(return_value=True),
			throw=throw,
			ValidationError=frappe.ValidationError,
			PermissionError=frappe.PermissionError,
		)
		self.patches = [
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal, "frappe", frappe_stub),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "can_access_branch_data", side_effect=branch_check),
			patch.object(billing_modal, "get_billing_modal_state", return_value=self.state),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=False),
			patch.object(billing_modal, "submitted_payment_exists", return_value=False),
		]
		for patcher in self.patches:
			patcher.start()
		return self

	def __exit__(self, exc_type, exc, tb):
		for patcher in reversed(self.patches):
			patcher.stop()
		return False


def get_app_file(relative_path: str) -> Path:
	return Path(__file__).resolve().parents[2] / relative_path


class TestBillingModalInvoiceHistoryRendering(TestCase):
	def test_invoice_history_rows_are_enriched_with_per_invoice_actions(self):
		from vetedge.services.billing_modal import enrich_invoice_history_for_modal

		rows = enrich_invoice_history_for_modal(
			[
				{
					"name": "ACC-SINV-PAID",
					"docstatus": 1,
					"grand_total": 11000,
					"paid_amount": 11000,
					"outstanding_amount": 0,
					"payment_state": "Paid",
					"source_doctype": "Veterinary Consultation",
					"source_name": "VCON-HISTORY",
				},
				{
					"name": "ACC-SINV-UNPAID",
					"docstatus": 1,
					"grand_total": 7000,
					"paid_amount": 0,
					"outstanding_amount": 7000,
					"payment_state": "Unpaid",
					"source_doctype": "Veterinary Consultation",
					"source_name": "VCON-HISTORY",
				},
				{
					"name": "ACC-SINV-DRAFT",
					"docstatus": 0,
					"grand_total": 2000,
					"paid_amount": 0,
					"outstanding_amount": 2000,
					"payment_state": "Draft",
				},
				{"docstatus": 1, "outstanding_amount": 1},
			]
		)

		self.assertEqual([row["name"] for row in rows], ["ACC-SINV-PAID", "ACC-SINV-UNPAID", "ACC-SINV-DRAFT"])
		paid, unpaid, draft = rows
		self.assertTrue(paid["can_open_invoice"])
		self.assertFalse(paid["can_pay_outstanding"])
		self.assertEqual(paid["action_label"], "Paid")
		self.assertTrue(unpaid["can_pay_outstanding"])
		self.assertTrue(unpaid["can_pay"])
		self.assertEqual(unpaid["action_label"], "Pay Outstanding")
		self.assertTrue(draft["can_submit_invoice"])
		self.assertFalse(draft["can_pay_outstanding"])
		self.assertEqual(draft["action_label"], "Open / Submit")

	def test_billing_modal_js_renders_billing_group_history_not_latest_only(self):
		js_path = Path(__file__).resolve().parents[1] / "public" / "js" / "billing_modal.js"
		source = js_path.read_text(encoding="utf-8")

		self.assertIn("function getLinkedInvoiceRows(state)", source)
		self.assertIn("state.invoice_history || state.billing_group_invoice_history", source)
		self.assertIn("Linked Invoice History", source)
		self.assertIn("Billing Group Payment Status", source)
		self.assertIn("Current Billing Cycle Status", source)
		self.assertIn("can_pay_outstanding", source)
		self.assertIn("submit-ledger-invoice", source)
