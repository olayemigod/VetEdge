from __future__ import annotations

from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import consultation_cancellation


class TestConsultationCancellationPreflight(TestCase):
	def build_preflight(
		self,
		invoices=None,
		labs=None,
		vaccinations=None,
		hospitalisations=None,
		stock_entries=None,
		billing_sessions=None,
		notifications=None,
		planned_treatments=None,
		outstanding_context=None,
	):
		with (
			patch.object(
				consultation_cancellation.frappe,
				"get_doc",
				return_value=frappe._dict(name="VCON-001", status="In Progress", planned_treatments=planned_treatments or []),
			),
			patch.object(consultation_cancellation, "get_consultation_billing_group_invoices", return_value=invoices or []),
			patch.object(consultation_cancellation, "get_linked_lab_orders", return_value=labs or []),
			patch.object(consultation_cancellation, "get_linked_vaccinations", return_value=vaccinations or []),
			patch.object(consultation_cancellation, "get_linked_hospitalisations", return_value=hospitalisations or []),
			patch.object(consultation_cancellation, "get_linked_stock_entries", return_value=stock_entries or []),
			patch.object(consultation_cancellation, "get_linked_billing_sessions", return_value=billing_sessions or []),
			patch.object(consultation_cancellation, "get_linked_notifications", return_value=notifications or []),
			patch.object(consultation_cancellation, "get_consultation_patient_outstanding_context", return_value=outstanding_context or []),
		):
			return consultation_cancellation.build_consultation_cancellation_preflight("VCON-001")

	def test_consultation_without_invoice_or_dependencies_can_cancel(self):
		preflight = self.build_preflight()

		self.assertTrue(preflight["can_cancel"])
		self.assertEqual(preflight["allowed_actions"], ["cancel_consultation"])
		self.assertEqual(preflight["billing_group_summary"]["payment_status"], "Not Billed")

	def test_draft_invoice_only_warns_but_allows_preflight(self):
		preflight = self.build_preflight(
			invoices=[
				{
					"invoice": "ACC-SINV-DRAFT",
					"docstatus": 0,
					"grand_total": 5000,
					"paid_amount": 0,
					"outstanding_amount": 5000,
				}
			]
		)

		self.assertTrue(preflight["can_cancel"])
		self.assertEqual(preflight["billing_group_summary"]["draft_invoice_count"], 1)
		self.assertEqual(preflight["warnings"][0]["type"], "draft_invoice")

	def test_old_patient_outstanding_invoice_is_informational_not_blocking(self):
		preflight = self.build_preflight(
			outstanding_context=[
				{
					"invoice": "ACC-SINV-OLD",
					"docstatus": 0,
					"grand_total": 7000,
					"paid_amount": 0,
					"outstanding_amount": 7000,
					"informational_only": True,
				}
			]
		)

		self.assertTrue(preflight["can_cancel"])
		self.assertEqual(preflight["linked_invoices"], [])
		self.assertEqual(preflight["outstanding_context"][0]["invoice"], "ACC-SINV-OLD")
		self.assertEqual(preflight["blockers"], [])

	def test_submitted_unpaid_invoice_blocks_direct_cancellation(self):
		preflight = self.build_preflight(
			invoices=[
				{
					"invoice": "ACC-SINV-UNPAID",
					"docstatus": 1,
					"grand_total": 7000,
					"paid_amount": 0,
					"outstanding_amount": 7000,
				}
			]
		)

		self.assertFalse(preflight["can_cancel"])
		self.assertEqual(preflight["blockers"][0]["type"], "submitted_invoice")
		self.assertEqual(preflight["allowed_actions"], ["admin_review_required"])

	def test_paid_invoice_blocks_and_returns_financial_resolution_actions(self):
		preflight = self.build_preflight(
			invoices=[
				{
					"invoice": "ACC-SINV-PAID",
					"docstatus": 1,
					"grand_total": 11000,
					"paid_amount": 11000,
					"outstanding_amount": 0,
				}
			]
		)

		self.assertFalse(preflight["can_cancel"])
		self.assertEqual(preflight["billing_group_summary"]["payment_status"], "Paid")
		self.assertIn("refund_required", preflight["allowed_actions"])
		self.assertIn("issue_customer_credit", preflight["allowed_actions"])
		self.assertIn(
			"Retain payment and cancel clinical record only",
			[row["label"] for row in preflight["allowed_action_options"]],
		)
		self.assertIn("Admin/accounting correction", [row["label"] for row in preflight["allowed_action_options"]])

	def test_partly_paid_billing_group_blocks_and_preserves_multiple_invoice_rows(self):
		preflight = self.build_preflight(
			invoices=[
				{"invoice": "ACC-SINV-00129", "docstatus": 1, "grand_total": 11000, "paid_amount": 11000, "outstanding_amount": 0},
				{"invoice": "ACC-SINV-00130", "docstatus": 1, "grand_total": 7000, "paid_amount": 0, "outstanding_amount": 7000},
				{"invoice": "ACC-SINV-00131", "docstatus": 1, "grand_total": 2000, "paid_amount": 2000, "outstanding_amount": 0},
			]
		)

		self.assertFalse(preflight["can_cancel"])
		self.assertEqual([row["invoice"] for row in preflight["linked_invoices"]], ["ACC-SINV-00129", "ACC-SINV-00130", "ACC-SINV-00131"])
		self.assertEqual(preflight["billing_group_summary"]["linked_invoice_count"], 3)
		self.assertEqual(preflight["billing_group_summary"]["paid_amount"], 13000)
		self.assertEqual(preflight["billing_group_summary"]["outstanding_amount"], 7000)
		self.assertEqual(preflight["billing_group_summary"]["payment_status"], "Partly Paid")
		self.assertIn("reschedule_consultation", preflight["allowed_actions"])

	def test_final_lab_vaccination_hospitalisation_and_submitted_stock_block(self):
		preflight = self.build_preflight(
			labs=[{"name": "VLAB-001", "status": "Reviewed", "docstatus": 0}],
			vaccinations=[{"name": "VVAC-001", "status": "Administered", "docstatus": 0}],
			hospitalisations=[{"name": "VHOS-001", "status": "Admitted", "docstatus": 0}],
			stock_entries=[{"name": "STE-001", "docstatus": 1}],
		)

		self.assertFalse(preflight["can_cancel"])
		self.assertIn("linked_lab_order", {row["type"] for row in preflight["blockers"]})
		self.assertIn("linked_vaccination", {row["type"] for row in preflight["blockers"]})
		self.assertIn("linked_hospitalisation", {row["type"] for row in preflight["blockers"]})
		self.assertIn("linked_stock_entry", {row["type"] for row in preflight["blockers"]})

	def test_draft_linked_clinical_docs_are_reported_as_warnings(self):
		preflight = self.build_preflight(
			labs=[{"name": "VLAB-DRAFT", "status": "Ordered", "docstatus": 0}],
			vaccinations=[{"name": "VVAC-DRAFT", "status": "Draft", "docstatus": 0}],
		)

		self.assertTrue(preflight["can_cancel"])
		self.assertEqual({row["type"] for row in preflight["warnings"]}, {"linked_lab_order", "linked_vaccination"})

	def test_source_linked_planned_treatment_rows_are_reported_without_removal(self):
		preflight = self.build_preflight(
			planned_treatments=[
				frappe._dict(
					name="PLAN-LAB",
					item="CBC",
					source_type="Lab Order",
					source_document="VLAB-001",
					billing_status="Draft Invoiced",
				)
			]
		)

		self.assertTrue(preflight["can_cancel"])
		self.assertEqual(preflight["linked_planned_treatments"][0]["source_document"], "VLAB-001")
		self.assertIn("source_linked_planned_treatment", {row["type"] for row in preflight["warnings"]})

	def test_only_current_consultation_planned_rows_are_reported(self):
		current_doc = frappe._dict(
			name="VCON-CURRENT",
			status="In Progress",
			planned_treatments=[
				frappe._dict(name="CURRENT-ROW", item="CBC", source_type="Lab Order", source_document="VLAB-CURRENT")
			],
		)
		with (
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=current_doc),
			patch.object(consultation_cancellation, "get_consultation_billing_group_invoices", return_value=[]),
			patch.object(consultation_cancellation, "get_consultation_patient_outstanding_context", return_value=[]),
			patch.object(consultation_cancellation, "get_linked_lab_orders", return_value=[]),
			patch.object(consultation_cancellation, "get_linked_vaccinations", return_value=[]),
			patch.object(consultation_cancellation, "get_linked_hospitalisations", return_value=[]),
			patch.object(consultation_cancellation, "get_linked_stock_entries", return_value=[]),
			patch.object(consultation_cancellation, "get_linked_billing_sessions", return_value=[]),
			patch.object(consultation_cancellation, "get_linked_notifications", return_value=[]),
		):
			preflight = consultation_cancellation.build_consultation_cancellation_preflight("VCON-CURRENT")

		self.assertEqual([row["name"] for row in preflight["linked_planned_treatments"]], ["CURRENT-ROW"])

	def test_validate_consultation_can_be_cancelled_throws_clear_blocker_message(self):
		with patch.object(
			consultation_cancellation,
			"build_consultation_cancellation_preflight",
			return_value={
				"can_cancel": False,
				"billing_group_summary": {"paid_amount": 1000},
				"blockers": [
					{"type": "paid_invoice", "message": "Invoice ACC-SINV-PAID has payment recorded and needs a financial resolution before cancellation."}
				],
				"warnings": [],
			},
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				consultation_cancellation.validate_consultation_can_be_cancelled("VCON-001")

		self.assertIn("Choose a financial resolution", str(ctx.exception))
		self.assertIn("Submitted invoices cannot be changed automatically", str(ctx.exception))

	def test_consultation_cancel_ui_renders_structured_preflight_sections(self):
		script_path = (
			__import__("pathlib").Path(__file__).resolve().parents[1]
			/ "veterinary"
			/ "doctype"
			/ "veterinary_consultation"
			/ "veterinary_consultation.js"
		)
		script = script_path.read_text()

		self.assertIn("show_consultation_cancellation_dialog", script)
		self.assertIn("Financial Resolution Options", script)
		self.assertIn("Other Outstanding Invoices for this Patient", script)
		self.assertIn("These invoices belong to this patient/customer but are not part of this consultation billing group", script)
		self.assertIn("perform_consultation_status_transition(frm, \"Cancelled\")", script)
