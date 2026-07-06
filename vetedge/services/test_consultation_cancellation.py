from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

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
		self.assertEqual(preflight["warnings"][0]["display_label"], "Invoice ACC-SINV-DRAFT")

	def test_default_consultation_fee_uses_human_friendly_label(self):
		row = frappe._dict(
			name="4tvh8ar53n",
			source_type="Consultation",
			source_detail_name="default_consultation_fee",
			description="consultation fee",
		)

		self.assertEqual(consultation_cancellation.get_planned_treatment_display_label(row), "Consultation Fee")

	def test_planned_treatment_warning_does_not_use_child_row_id_as_primary_label(self):
		preflight = self.build_preflight(
			planned_treatments=[
				frappe._dict(
					name="4tvh8ar53n",
					source_type="Consultation",
					source_doctype="Veterinary Consultation",
					source_document="VCON-001",
					source_detail_name="default_consultation_fee",
					description="consultation fee",
				)
			]
		)

		self.assertTrue(preflight["can_cancel"])
		self.assertEqual(preflight["linked_planned_treatments"][0]["display_label"], "Consultation Fee")
		warning = preflight["warnings"][0]
		self.assertEqual(warning["display_label"], "Consultation Fee")
		self.assertIn("Consultation Fee", warning["message"])
		self.assertNotIn("4tvh8ar53n", warning["message"])

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

	def test_execute_safe_cancellation_sets_cancelled_after_cleanup(self):
		doc = frappe._dict(name="VCON-001", status="In Progress")
		doc.save = Mock()
		with (
			patch.object(consultation_cancellation, "validate_consultation_can_be_cancelled", return_value={"can_cancel": True, "warnings": []}) as validate,
			patch.object(
				consultation_cancellation,
				"cleanup_safe_draft_dependencies",
				return_value={"cleaned_draft_invoices": [], "skipped_draft_invoices": [], "closed_billing_sessions": [], "preserved_references": []},
			) as cleanup,
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=doc),
		):
			result = consultation_cancellation.execute_consultation_cancellation("VCON-001")

		validate.assert_called_once_with("VCON-001")
		cleanup.assert_called_once()
		self.assertEqual(doc.status, "Cancelled")
		doc.save.assert_called_once()
		self.assertEqual(result["status"], "Cancelled")

	def test_execute_safe_cancellation_reports_preserved_patient_outstanding_context(self):
		doc = frappe._dict(name="VCON-001", status="In Progress")
		doc.save = Mock()
		with (
			patch.object(
				consultation_cancellation,
				"validate_consultation_can_be_cancelled",
				return_value={
					"can_cancel": True,
					"warnings": [],
					"outstanding_context": [{"invoice": "ACC-SINV-OLD", "context_type": "patient_outstanding"}],
				},
			),
			patch.object(
				consultation_cancellation,
				"cleanup_safe_draft_dependencies",
				return_value={"cleaned_draft_invoices": [], "skipped_draft_invoices": [], "closed_billing_sessions": [], "preserved_references": []},
			),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=doc),
		):
			result = consultation_cancellation.execute_consultation_cancellation("VCON-001")

		self.assertEqual(result["preserved_patient_outstanding_invoices"], ["ACC-SINV-OLD"])

	def test_execute_safe_cancellation_blocks_when_preflight_blocks(self):
		with patch.object(consultation_cancellation, "validate_consultation_can_be_cancelled", side_effect=frappe.ValidationError):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.execute_consultation_cancellation("VCON-001")

	def test_safe_cancellation_cleanup_ignores_patient_outstanding_context(self):
		with (
			patch.object(consultation_cancellation, "cleanup_draft_invoice_for_consultation") as cleanup_invoice,
			patch.object(consultation_cancellation, "close_safe_draft_billing_sessions", return_value=[]),
		):
			result = consultation_cancellation.cleanup_safe_draft_dependencies(
				"VCON-001",
				{
					"linked_invoices": [],
					"outstanding_context": [{"invoice": "ACC-SINV-OLD", "docstatus": 0}],
				},
			)

		cleanup_invoice.assert_not_called()
		self.assertEqual(result["cleaned_draft_invoices"], [])

	def test_safe_cancellation_cleanup_deletes_safe_draft_invoice(self):
		with (
			patch.object(consultation_cancellation, "is_draft_invoice_safe_for_consultation_cleanup", return_value=True),
			patch.object(consultation_cancellation, "cleanup_draft_invoice_for_consultation") as cleanup_invoice,
			patch.object(consultation_cancellation, "close_safe_draft_billing_sessions", return_value=["VBS-001"]),
		):
			result = consultation_cancellation.cleanup_safe_draft_dependencies(
				"VCON-001",
				{"linked_invoices": [{"invoice": "ACC-SINV-DRAFT", "docstatus": 0}]},
			)

		cleanup_invoice.assert_called_once_with("ACC-SINV-DRAFT", "VCON-001")
		self.assertEqual(result["cleaned_draft_invoices"], ["ACC-SINV-DRAFT"])
		self.assertEqual(result["closed_billing_sessions"], ["VBS-001"])

	def test_safe_draft_sales_invoice_cleanup_uses_narrow_internal_delete(self):
		with (
			patch.object(consultation_cancellation, "is_draft_invoice_safe_for_consultation_cleanup", return_value=True),
			patch.object(consultation_cancellation.frappe, "delete_doc") as delete_doc,
		):
			consultation_cancellation.delete_safe_draft_sales_invoice("ACC-SINV-DRAFT", "VCON-001")

		delete_doc.assert_called_once_with("Sales Invoice", "ACC-SINV-DRAFT", ignore_permissions=True)

	def test_unproven_draft_sales_invoice_cleanup_returns_friendly_blocker(self):
		with (
			patch.object(consultation_cancellation, "is_draft_invoice_safe_for_consultation_cleanup", return_value=False),
			patch.object(consultation_cancellation.frappe, "delete_doc") as delete_doc,
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				consultation_cancellation.delete_safe_draft_sales_invoice("ACC-SINV-OTHER", "VCON-001")

		delete_doc.assert_not_called()
		self.assertIn("Please ask Accounts/Admin to review it", str(ctx.exception))

	def test_safe_cancellation_cleanup_rejects_draft_invoice_from_another_context(self):
		with patch.object(consultation_cancellation, "is_draft_invoice_safe_for_consultation_cleanup", return_value=False):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.cleanup_safe_draft_dependencies(
					"VCON-001",
					{"linked_invoices": [{"invoice": "ACC-SINV-OTHER", "docstatus": 0}]},
				)

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

	def build_paid_resolution_preflight(self):
		return {
			"can_cancel": False,
			"consultation": "VCON-001",
			"blockers": [{"type": "paid_invoice", "invoice": "ACC-SINV-PAID"}],
			"warnings": [],
			"allowed_actions": consultation_cancellation.FINANCIAL_RESOLUTION_ACTIONS[:],
			"linked_invoices": [
				{
					"invoice": "ACC-SINV-PAID",
					"docstatus": 1,
					"status": "Paid",
					"payment_state": "Paid",
					"grand_total": 11000,
					"paid_amount": 11000,
					"outstanding_amount": 0,
				}
			],
			"billing_group_summary": {"paid_amount": 11000, "outstanding_amount": 0, "submitted_invoice_count": 1},
		}

	def test_authorized_user_can_record_cancellation_resolution_decision(self):
		consultation = frappe._dict(
			name="VCON-001",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
			company="VetCo",
			status="Ready for Treatment",
		)
		decision = frappe._dict(name="VCCR-001")
		decision.insert = Mock()
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "safe_doctype_exists", return_value=True),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=None),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=consultation),
			patch.object(consultation_cancellation.frappe, "new_doc", return_value=decision),
			patch.object(consultation_cancellation.frappe, "get_roles", return_value=["Accounts User"]),
			patch.object(consultation_cancellation.frappe, "delete_doc") as delete_doc,
		):
			result = consultation_cancellation.record_consultation_cancellation_resolution(
				"VCON-001",
				"refund_required",
				reason="Owner requested refund review.",
			)

		decision.insert.assert_called_once()
		delete_doc.assert_not_called()
		self.assertEqual(decision.consultation, "VCON-001")
		self.assertEqual(decision.patient, "VP-001")
		self.assertEqual(decision.customer, "CUST-001")
		self.assertEqual(decision.resolution_action_key, "refund_required")
		self.assertEqual(decision.resolution_action, "Refund required")
		self.assertEqual(decision.resolution_status, "Pending Review")
		self.assertEqual(decision.reason, "Owner requested refund review.")
		self.assertEqual(decision.billing_group_paid_amount, 11000)
		self.assertEqual(result["resolution_action_key"], "refund_required")
		self.assertEqual(result["related_invoices"][0]["invoice"], "ACC-SINV-PAID")
		self.assertNotEqual(consultation.status, "Cancelled")

	def test_invalid_cancellation_resolution_action_is_rejected(self):
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation.frappe, "get_roles", return_value=["Accounts User"]),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.record_consultation_cancellation_resolution("VCON-001", "delete_invoice")

	def test_resolution_action_not_allowed_by_preflight_is_rejected(self):
		preflight = self.build_paid_resolution_preflight()
		preflight["allowed_actions"] = ["refund_required"]
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=preflight),
			patch.object(consultation_cancellation.frappe, "get_roles", return_value=["Accounts User"]),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.record_consultation_cancellation_resolution("VCON-001", "issue_customer_credit")

	def test_approved_cancellation_resolution_is_not_overwritten(self):
		existing = frappe._dict(name="VCCR-APPROVED", resolution_status="Approved")
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "safe_doctype_exists", return_value=True),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=existing),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=frappe._dict(name="VCON-001")),
			patch.object(consultation_cancellation.frappe, "get_roles", return_value=["Accounts User"]),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.record_consultation_cancellation_resolution("VCON-001", "refund_required")

	def test_unauthorized_user_cannot_record_cancellation_resolution(self):
		with patch.object(consultation_cancellation.frappe, "get_roles", return_value=["VetEdge Doctor"]):
			with self.assertRaises(frappe.PermissionError):
				consultation_cancellation.validate_user_can_record_cancellation_resolution("doctor@example.com")

	def build_retain_payment_resolution(self, status="Pending Review"):
		resolution = frappe._dict(
			name="VCCR-001",
			consultation="VCON-001",
			resolution_action_key="retain_payment_clinical_cancel_only",
			resolution_action="Retain payment and cancel clinical record only",
			resolution_status=status,
			notes="Resolution decision only.",
		)
		resolution.save = Mock()
		return resolution

	def build_reschedule_resolution(self, status="Pending Review"):
		resolution = frappe._dict(
			name="VCCR-RESCHEDULE",
			consultation="VCON-001",
			resolution_action_key="reschedule_consultation",
			resolution_action="Reschedule consultation",
			resolution_status=status,
			reason="Owner requested a new visit.",
			notes="Resolution decision only.",
			linked_new_appointment=None,
			linked_new_consultation=None,
		)
		resolution.save = Mock()
		return resolution

	def build_manual_accounting_resolution(self, action_key="refund_required", status="Approved"):
		resolution = frappe._dict(
			name="VCCR-MANUAL",
			consultation="VCON-001",
			resolution_action_key=action_key,
			resolution_action=consultation_cancellation.RESOLUTION_ACTION_LABELS[action_key],
			resolution_status=status,
			notes="Resolution decision only.",
		)
		resolution.save = Mock()
		return resolution

	def test_paid_consultation_without_resolution_cannot_retain_payment_cancel(self):
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=None),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.execute_retain_payment_consultation_cancellation("VCON-001")

	def test_paid_consultation_with_refund_resolution_cannot_retain_payment_cancel(self):
		resolution = self.build_retain_payment_resolution()
		resolution.resolution_action_key = "refund_required"
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.execute_retain_payment_consultation_cancellation("VCON-001")

	def test_pending_review_retain_payment_resolution_cannot_clinically_cancel(self):
		resolution = self.build_retain_payment_resolution(status="Pending Review")
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.execute_retain_payment_consultation_cancellation("VCON-001")

	def test_approved_retain_payment_resolution_can_clinically_cancel_by_authorized_user(self):
		consultation = frappe._dict(name="VCON-001", status="Ready for Treatment")
		consultation.save = Mock()
		resolution = self.build_retain_payment_resolution(status="Approved")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=consultation),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
			patch.object(consultation_cancellation.frappe, "delete_doc") as delete_doc,
		):
			result = consultation_cancellation.execute_retain_payment_consultation_cancellation("VCON-001")

		self.assertEqual(consultation.status, "Cancelled")
		consultation.save.assert_called_once()
		self.assertEqual(resolution.resolution_status, "Completed")
		resolution.save.assert_called_once()
		delete_doc.assert_not_called()
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["consultation_status"], "Cancelled")
		self.assertEqual(result["resolution"]["resolution_status"], "Completed")
		self.assertEqual(result["resolution_status"], "Completed")
		self.assertEqual(result["invoices_preserved"], ["ACC-SINV-PAID"])
		self.assertTrue(result["payments_preserved"])
		self.assertIn("No accounting reversal", result["message"])

	def test_retain_payment_cancellation_uses_internal_cancel_flag_for_consultation_save(self):
		consultation = frappe._dict(name="VCON-001", status="Ready for Treatment")
		consultation.save = Mock()
		resolution = self.build_retain_payment_resolution(status="Approved")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=consultation),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
			patch.object(consultation_cancellation, "run_with_retain_payment_cancellation_flag") as run_with_flag,
		):
			run_with_flag.side_effect = lambda callback: callback()
			consultation_cancellation.execute_retain_payment_consultation_cancellation("VCON-001")

		run_with_flag.assert_called_once_with(consultation.save)
		consultation.save.assert_called_once()

	def test_normal_safe_cancellation_does_not_use_retain_payment_flag(self):
		doc = frappe._dict(name="VCON-001", status="In Progress")
		doc.save = Mock()
		with (
			patch.object(consultation_cancellation, "validate_consultation_can_be_cancelled", return_value={"can_cancel": True, "warnings": []}),
			patch.object(
				consultation_cancellation,
				"cleanup_safe_draft_dependencies",
				return_value={"cleaned_draft_invoices": [], "skipped_draft_invoices": [], "closed_billing_sessions": [], "preserved_references": []},
			),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=doc),
			patch.object(consultation_cancellation, "run_with_retain_payment_cancellation_flag") as run_with_flag,
		):
			consultation_cancellation.execute_consultation_cancellation("VCON-001")

		run_with_flag.assert_not_called()
		doc.save.assert_called_once()

	def test_retain_payment_requires_payment_evidence(self):
		preflight = self.build_paid_resolution_preflight()
		preflight["billing_group_summary"] = {"paid_amount": 0, "outstanding_amount": 11000, "submitted_invoice_count": 1}
		resolution = self.build_retain_payment_resolution(status="Approved")
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=preflight),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.execute_retain_payment_consultation_cancellation("VCON-001")

	def test_unauthorized_user_cannot_execute_retain_payment_cancellation(self):
		with patch.object(consultation_cancellation.frappe, "get_roles", return_value=["VetEdge Doctor"]):
			with self.assertRaises(frappe.PermissionError):
				consultation_cancellation.validate_user_can_execute_retain_payment_cancellation("doctor@example.com")

	def test_accounts_user_can_approve_cancellation_resolution(self):
		resolution = self.build_retain_payment_resolution(status="Pending Review")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation, "require_internal_user"),
			patch.object(consultation_cancellation, "validate_user_can_approve_cancellation_resolution"),
			patch.object(consultation_cancellation, "safe_doctype_exists", return_value=True),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=resolution),
			patch.object(consultation_cancellation, "can_access_consultation"),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
			patch.object(consultation_cancellation.frappe, "session", frappe._dict(user="accounts@example.com")),
			patch.object(consultation_cancellation, "now_datetime", return_value="2026-07-06 10:00:00"),
		):
			result = consultation_cancellation.update_consultation_cancellation_resolution_status(
				"VCCR-001",
				"Approved",
				note="Approved by accounts.",
			)

		self.assertEqual(resolution.resolution_status, "Approved")
		self.assertEqual(resolution.approved_by, "accounts@example.com")
		self.assertTrue(resolution.approved_on)
		self.assertIn("Approved by accounts.", resolution.notes)
		resolution.save.assert_called_once()
		self.assertEqual(result["resolution_status"], "Approved")

	def test_doctor_cannot_approve_cancellation_resolution(self):
		with patch.object(consultation_cancellation.frappe, "get_roles", return_value=["VetEdge Doctor"]):
			with self.assertRaises(frappe.PermissionError):
				consultation_cancellation.validate_user_can_approve_cancellation_resolution("doctor@example.com")

	def test_rejected_retain_payment_resolution_cannot_execute(self):
		resolution = self.build_retain_payment_resolution(status="Rejected")
		with patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.get_valid_retain_payment_resolution_doc("VCON-001")

	def test_pending_review_reschedule_resolution_cannot_execute(self):
		resolution = self.build_reschedule_resolution(status="Pending Review")
		with patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.get_valid_reschedule_resolution_doc("VCON-001")

	def test_retain_payment_resolution_cannot_use_reschedule_execution(self):
		resolution = self.build_retain_payment_resolution(status="Approved")
		with patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.get_valid_reschedule_resolution_doc("VCON-001")

	def test_approved_reschedule_resolution_creates_linked_appointment(self):
		resolution = self.build_reschedule_resolution(status="Approved")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation, "build_consultation_cancellation_preflight", return_value=self.build_paid_resolution_preflight()),
			patch.object(consultation_cancellation, "get_open_cancellation_resolution_doc", return_value=resolution),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="Ready for Treatment"),
			patch(
				"vetedge.services.appointment_flow.create_follow_up_from_consultation",
				return_value={"name": "VAPT-RESCHEDULE-001", "appointment_title": "Buddy follow up"},
			) as create_follow_up,
		):
			result = consultation_cancellation.execute_reschedule_consultation_resolution(
				"VCON-001",
				appointment_datetime="2026-07-15 09:00:00",
				reason="Owner requested a later appointment.",
			)

		create_follow_up.assert_called_once()
		self.assertEqual(create_follow_up.call_args.args[0], "VCON-001")
		self.assertEqual(create_follow_up.call_args.kwargs["appointment_datetime"], "2026-07-15 09:00:00")
		self.assertIn("Original submitted invoices and payments remain unchanged", create_follow_up.call_args.kwargs["notes"])
		self.assertEqual(resolution.linked_new_appointment, "VAPT-RESCHEDULE-001")
		self.assertIsNone(resolution.linked_new_consultation)
		self.assertEqual(resolution.resolution_status, "Completed")
		resolution.save.assert_called_once()
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["consultation_status"], "Ready for Treatment")
		self.assertEqual(result["resolution_status"], "Completed")
		self.assertEqual(result["linked_new_appointment"], "VAPT-RESCHEDULE-001")
		self.assertEqual(result["invoices_preserved"], ["ACC-SINV-PAID"])
		self.assertTrue(result["payments_preserved"])
		self.assertIn("Original invoices and payments were preserved", result["message"])

	def test_reschedule_execution_does_not_support_new_consultation_creation_yet(self):
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.execute_reschedule_consultation_resolution(
				"VCON-001",
				appointment_datetime="2026-07-15 09:00:00",
				create_new_consultation=True,
			)

	def test_unauthorized_user_cannot_execute_reschedule_resolution(self):
		with patch.object(consultation_cancellation.frappe, "get_roles", return_value=["VetEdge Doctor"]):
			with self.assertRaises(frappe.PermissionError):
				consultation_cancellation.validate_user_can_execute_reschedule_cancellation_resolution("doctor@example.com")

	def test_front_desk_can_execute_reschedule_resolution(self):
		with patch.object(consultation_cancellation.frappe, "get_roles", return_value=["VetEdge Front Desk"]):
			consultation_cancellation.validate_user_can_execute_reschedule_cancellation_resolution("frontdesk@example.com")

	def test_approved_refund_resolution_can_be_manually_completed(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation.frappe, "session", frappe._dict(user="accounts@example.com")),
			patch.object(consultation_cancellation, "now_datetime", return_value="2026-07-06 12:00:00"),
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="Ready for Treatment"),
			patch.object(consultation_cancellation.frappe.db, "exists", return_value=True),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
		):
			result = consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Refund processed manually by accounts.",
				accounting_reference_doctype="Payment Entry",
				accounting_reference_name="PE-REFUND-001",
				resolution_amount=11000,
				resolution_date="2026-07-06",
			)

		self.assertEqual(resolution.resolution_status, "Completed")
		self.assertIn("Refund processed manually by accounts.", resolution.notes)
		self.assertIn("PE-REFUND-001", resolution.notes)
		self.assertIn("did not create or mutate", resolution.notes)
		self.assertEqual(resolution.accounting_reference_doctype, "Payment Entry")
		self.assertEqual(resolution.accounting_reference_name, "PE-REFUND-001")
		self.assertEqual(resolution.resolution_amount, 11000)
		self.assertEqual(resolution.resolution_date, "2026-07-06")
		self.assertEqual(resolution.status_outcome, "No Status Change")
		self.assertEqual(resolution.completion_note, "Refund processed manually by accounts.")
		self.assertEqual(resolution.completed_by, "accounts@example.com")
		self.assertEqual(resolution.completed_on, "2026-07-06 12:00:00")
		resolution.save.assert_called_once()
		self.assertEqual(result["consultation_status"], "Ready for Treatment")
		self.assertEqual(result["resolution_status"], "Completed")
		self.assertEqual(result["status_outcome"], "no_status_change")
		self.assertEqual(result["consultation_status_before"], "Ready for Treatment")
		self.assertEqual(result["consultation_status_after"], "Ready for Treatment")
		self.assertEqual(result["accounting_reference_doctype"], "Payment Entry")
		self.assertEqual(result["accounting_reference_name"], "PE-REFUND-001")
		self.assertEqual(result["resolution_amount"], 11000)
		self.assertTrue(result["accounting_documents_preserved"])

	def test_approved_credit_resolution_can_be_manually_completed(self):
		resolution = self.build_manual_accounting_resolution("issue_customer_credit", status="Approved")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation.frappe, "session", frappe._dict(user="accounts@example.com")),
			patch.object(consultation_cancellation, "now_datetime", return_value="2026-07-06 12:00:00"),
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="Awaiting Payment"),
			patch.object(consultation_cancellation.frappe.db, "exists", return_value=True),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
		):
			result = consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Credit note handled manually.",
				accounting_reference_doctype="Sales Invoice",
				accounting_reference_name="ACC-SINV-RETURN-001",
				resolution_amount=8000,
				resolution_date="2026-07-06",
			)

		self.assertEqual(resolution.resolution_status, "Completed")
		self.assertIn("Credit note handled manually.", resolution.notes)
		self.assertEqual(resolution.accounting_reference_doctype, "Sales Invoice")
		self.assertEqual(resolution.accounting_reference_name, "ACC-SINV-RETURN-001")
		self.assertEqual(resolution.resolution_amount, 8000)
		self.assertEqual(resolution.status_outcome, "No Status Change")
		self.assertEqual(result["consultation_status"], "Awaiting Payment")

	def test_approved_refund_resolution_can_cancel_consultation_after_financial_resolution(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
		consultation = frappe._dict(name="VCON-001", status="Ready for Treatment")
		consultation.save = Mock()
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation.frappe, "session", frappe._dict(user="accounts@example.com")),
			patch.object(consultation_cancellation, "now_datetime", return_value="2026-07-06 12:00:00"),
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="Ready for Treatment"),
			patch.object(consultation_cancellation.frappe.db, "exists", return_value=True),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=consultation),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
			patch.object(consultation_cancellation, "run_with_financial_resolution_cancellation_flag") as run_with_flag,
		):
			run_with_flag.side_effect = lambda callback: callback()
			result = consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Refund completed and service cancelled.",
				accounting_reference_doctype="Payment Entry",
				accounting_reference_name="PE-REFUND-001",
				resolution_amount=11000,
				resolution_date="2026-07-06",
				status_outcome="cancel_consultation_after_financial_resolution",
			)

		run_with_flag.assert_called_once_with(consultation.save)
		consultation.save.assert_called_once()
		self.assertEqual(consultation.status, "Cancelled")
		self.assertEqual(resolution.resolution_status, "Completed")
		self.assertEqual(resolution.status_outcome, "Cancel Consultation After Financial Resolution")
		self.assertEqual(result["consultation_status_before"], "Ready for Treatment")
		self.assertEqual(result["consultation_status_after"], "Cancelled")
		self.assertEqual(result["consultation_status"], "Cancelled")
		self.assertEqual(result["status_outcome"], "cancel_consultation_after_financial_resolution")

	def test_approved_credit_resolution_can_cancel_consultation_after_financial_resolution(self):
		resolution = self.build_manual_accounting_resolution("issue_customer_credit", status="Approved")
		consultation = frappe._dict(name="VCON-001", status="Awaiting Payment")
		consultation.save = Mock()
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation.frappe, "session", frappe._dict(user="accounts@example.com")),
			patch.object(consultation_cancellation, "now_datetime", return_value="2026-07-06 12:00:00"),
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="Awaiting Payment"),
			patch.object(consultation_cancellation.frappe.db, "exists", return_value=True),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=consultation),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
			patch.object(consultation_cancellation, "run_with_financial_resolution_cancellation_flag") as run_with_flag,
		):
			run_with_flag.side_effect = lambda callback: callback()
			result = consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Credit issued because service was cancelled.",
				accounting_reference_doctype="Sales Invoice",
				accounting_reference_name="ACC-SINV-RETURN-001",
				resolution_amount=8000,
				resolution_date="2026-07-06",
				status_outcome="Cancel Consultation After Financial Resolution",
			)

		self.assertEqual(consultation.status, "Cancelled")
		self.assertEqual(resolution.resolution_status, "Completed")
		self.assertEqual(result["consultation_status_after"], "Cancelled")
		self.assertEqual(result["status_outcome"], "cancel_consultation_after_financial_resolution")

	def test_approved_admin_correction_resolution_can_be_manually_completed(self):
		resolution = self.build_manual_accounting_resolution("admin_accounting_correction", status="Approved")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation.frappe, "session", frappe._dict(user="accounts@example.com")),
			patch.object(consultation_cancellation, "now_datetime", return_value="2026-07-06 12:00:00"),
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="In Progress"),
			patch.object(consultation_cancellation.frappe.db, "exists", return_value=True),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
		):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Admin correction verified outside VetEdge.",
				accounting_reference_doctype="Journal Entry",
				accounting_reference_name="JE-001",
				resolution_date="2026-07-06",
			)

		self.assertEqual(resolution.resolution_status, "Completed")
		self.assertIn("JE-001", resolution.notes)
		self.assertEqual(resolution.accounting_reference_doctype, "Journal Entry")
		self.assertEqual(resolution.accounting_reference_name, "JE-001")
		self.assertEqual(resolution.status_outcome, "No Status Change")

	def test_admin_accounting_correction_cannot_cancel_consultation_after_financial_resolution(self):
		resolution = self.build_manual_accounting_resolution("admin_accounting_correction", status="Approved")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Correction done.",
				accounting_reference_doctype="Journal Entry",
				accounting_reference_name="JE-001",
				resolution_date="2026-07-06",
				status_outcome="cancel_consultation_after_financial_resolution",
			)

	def test_already_cancelled_consultation_cannot_be_cancelled_again_after_financial_resolution(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
		consultation = frappe._dict(name="VCON-001", status="Cancelled")
		consultation.save = Mock()
		with (
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="Cancelled"),
			patch.object(consultation_cancellation.frappe.db, "exists", return_value=True),
			patch.object(consultation_cancellation.frappe, "get_doc", return_value=consultation),
		):
			with self.assertRaises(frappe.ValidationError):
				consultation_cancellation.complete_manual_accounting_resolution(
					resolution,
					completion_note="Refund completed.",
					accounting_reference_doctype="Payment Entry",
					accounting_reference_name="PE-REFUND-001",
					resolution_amount=11000,
					resolution_date="2026-07-06",
					status_outcome="cancel_consultation_after_financial_resolution",
				)

		consultation.save.assert_not_called()
		resolution.save.assert_not_called()

	def test_approved_refund_resolution_cannot_complete_with_note_only(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Refund done.",
				resolution_date="2026-07-06",
			)

	def test_approved_credit_resolution_cannot_complete_with_note_only(self):
		resolution = self.build_manual_accounting_resolution("issue_customer_credit", status="Approved")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Credit done.",
				resolution_amount=1000,
				resolution_date="2026-07-06",
			)

	def test_admin_correction_resolution_requires_accounting_reference(self):
		resolution = self.build_manual_accounting_resolution("admin_accounting_correction", status="Approved")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Correction done.",
				resolution_date="2026-07-06",
			)

	def test_refund_and_credit_completion_require_positive_amount(self):
		for action in ("refund_required", "issue_customer_credit"):
			with self.subTest(action=action):
				resolution = self.build_manual_accounting_resolution(action, status="Approved")
				with self.assertRaises(frappe.ValidationError):
					consultation_cancellation.complete_manual_accounting_resolution(
						resolution,
						completion_note="Done.",
						accounting_reference_doctype="Payment Entry",
						accounting_reference_name="PE-001",
						resolution_amount=0,
						resolution_date="2026-07-06",
					)

	def test_external_reference_without_accounting_document_requires_manager_role(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
		with patch.object(consultation_cancellation.frappe, "get_roles", return_value=["Accounts User"]):
			with self.assertRaises(frappe.PermissionError):
				consultation_cancellation.complete_manual_accounting_resolution(
					resolution,
					completion_note="External refund confirmed.",
					accounting_reference_name="BANK-REF-001",
					resolution_amount=11000,
					resolution_date="2026-07-06",
					external_reference=True,
				)

	def test_system_manager_can_complete_with_external_reference(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
		meta = Mock()
		meta.has_field.return_value = True
		with (
			patch.object(consultation_cancellation.frappe, "session", frappe._dict(user="manager@example.com")),
			patch.object(consultation_cancellation.frappe, "get_roles", return_value=["System Manager"]),
			patch.object(consultation_cancellation, "now_datetime", return_value="2026-07-06 12:00:00"),
			patch.object(consultation_cancellation.frappe.db, "get_value", return_value="In Progress"),
			patch.object(consultation_cancellation.frappe, "get_meta", return_value=meta),
		):
			result = consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="External refund confirmed by bank advice.",
				accounting_reference_name="BANK-REF-001",
				resolution_amount=11000,
				resolution_date="2026-07-06",
				external_reference=True,
			)

		self.assertEqual(resolution.resolution_status, "Completed")
		self.assertEqual(resolution.accounting_reference_doctype, "External Reference")
		self.assertEqual(resolution.accounting_reference_name, "BANK-REF-001")
		self.assertEqual(resolution.external_reference, 1)
		self.assertEqual(result["external_reference"], True)

	def test_pending_review_manual_accounting_resolution_cannot_complete(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Pending Review")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Done.",
				accounting_reference_doctype="Payment Entry",
				accounting_reference_name="PE-001",
				resolution_amount=1000,
				resolution_date="2026-07-06",
			)

	def test_rejected_manual_accounting_resolution_cannot_complete(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Rejected")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Done.",
				accounting_reference_doctype="Payment Entry",
				accounting_reference_name="PE-001",
				resolution_amount=1000,
				resolution_date="2026-07-06",
			)

	def test_completed_manual_accounting_resolution_cannot_complete_again(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Completed")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(
				resolution,
				completion_note="Done again.",
				accounting_reference_doctype="Payment Entry",
				accounting_reference_name="PE-001",
				resolution_amount=1000,
				resolution_date="2026-07-06",
			)

	def test_manual_accounting_resolution_completion_requires_note(self):
		resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
		with self.assertRaises(frappe.ValidationError):
			consultation_cancellation.complete_manual_accounting_resolution(resolution, completion_note="")

	def test_retain_payment_and_reschedule_decisions_cannot_use_manual_accounting_completion(self):
		for action in ("retain_payment_clinical_cancel_only", "reschedule_consultation"):
			with self.subTest(action=action):
				resolution = self.build_manual_accounting_resolution("refund_required", status="Approved")
				resolution.resolution_action_key = action
				with self.assertRaises(frappe.ValidationError):
					consultation_cancellation.complete_manual_accounting_resolution(
						resolution,
						completion_note="Done.",
						accounting_reference_doctype="Payment Entry",
						accounting_reference_name="PE-001",
						resolution_amount=1000,
						resolution_date="2026-07-06",
					)

	def test_doctor_and_front_desk_cannot_complete_manual_accounting_resolution(self):
		for role in ("VetEdge Doctor", "VetEdge Front Desk"):
			with self.subTest(role=role), patch.object(consultation_cancellation.frappe, "get_roles", return_value=[role]):
				with self.assertRaises(frappe.PermissionError):
					consultation_cancellation.validate_user_can_complete_manual_accounting_resolution("user@example.com")

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
		self.assertIn("vetedge.services.consultation_cancellation.cancel_consultation_safely", script)
		self.assertIn("Recorded Resolution Decision", script)
		self.assertIn("vetedge.services.consultation_cancellation.record_consultation_cancellation_resolution", script)
		self.assertIn("Record Resolution Request", script)
		self.assertIn("Resolution request recorded for approval", script)
		self.assertIn("Recording a resolution request does not cancel this consultation", script)
		self.assertIn("Resolution pending approval.", script)
		self.assertIn("vetedge.services.consultation_cancellation.approve_consultation_cancellation_resolution", script)
		self.assertIn("Approve Resolution", script)
		self.assertIn("Approval authorizes the next step but does not cancel this consultation", script)
		self.assertIn("Cancel Clinical Record and Retain Payment", script)
		self.assertIn("vetedge.services.consultation_cancellation.retain_payment_and_cancel_consultation", script)
		self.assertIn("Submitted invoices and payments will remain unchanged", script)
		self.assertIn("Create Reschedule Appointment", script)
		self.assertIn("vetedge.services.consultation_cancellation.execute_consultation_reschedule_resolution", script)
		self.assertIn("Original submitted invoices and payments remain unchanged", script)
		self.assertIn("Mark Refund Resolution Completed", script)
		self.assertIn("Mark Credit Resolution Completed", script)
		self.assertIn("Mark Admin Correction Completed", script)
		self.assertIn("vetedge.services.consultation_cancellation.complete_consultation_cancellation_resolution_manually", script)
		self.assertIn("Record refund accounting evidence before completing this resolution", script)
		self.assertIn("accounting_reference_doctype", script)
		self.assertIn("accounting_reference_name", script)
		self.assertIn("resolution_amount", script)
		self.assertIn("resolution_date", script)
		self.assertIn("external_reference", script)
		self.assertIn("status_outcome", script)
		self.assertIn("Cancel Consultation After Financial Resolution", script)
		self.assertIn("Choose Cancel only if this refund means the consultation/service will not continue", script)
		self.assertIn("Admin corrections do not change consultation status in this phase", script)
		self.assertIn("VetEdge will not create refunds, Credit Notes, Payment Entries, accounting reversals, or apply credit to a rescheduled consultation", script)
		self.assertNotIn("Apply Credit to Rescheduled Consultation", script)
