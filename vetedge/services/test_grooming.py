from __future__ import annotations

from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from vetedge.services import grooming


class GroomingWorkflowStatusTestCase(unittest.TestCase):
	def test_unpaid_billed_session_becomes_awaiting_payment(self):
		doc = SimpleNamespace(status="Draft", linked_invoice="SINV-001")
		invoice = SimpleNamespace(docstatus=1, outstanding_amount=100, grand_total=100)
		with patch.object(grooming, "is_grooming_billing_enabled", return_value=True), patch.object(grooming.frappe, "get_doc", return_value=invoice), patch.object(grooming, "get_invoice_payment_status", return_value="Unpaid"):
			self.assertEqual(grooming.get_grooming_session_workflow_status(doc), "Awaiting Payment")

	def test_paid_billed_session_becomes_pending_grooming(self):
		doc = SimpleNamespace(status="Awaiting Payment", linked_invoice="SINV-001")
		invoice = SimpleNamespace(docstatus=1, outstanding_amount=0, grand_total=100)
		with patch.object(grooming, "is_grooming_billing_enabled", return_value=True), patch.object(grooming.frappe, "get_doc", return_value=invoice), patch.object(grooming, "get_invoice_payment_status", return_value=grooming.PAID_STATUS):
			self.assertEqual(grooming.get_grooming_session_workflow_status(doc), "Pending Grooming")

	def test_in_progress_session_is_not_downgraded_by_billing(self):
		doc = SimpleNamespace(status="In Progress", linked_invoice="SINV-001")
		with patch.object(grooming, "is_grooming_billing_enabled", return_value=True):
			self.assertEqual(grooming.get_grooming_session_workflow_status(doc), "In Progress")

	def test_completed_appointment_without_completed_session_is_blocked(self):
		doc = SimpleNamespace(name="PGAP-2026-00001", status="Completed")
		previous = SimpleNamespace(status="In Progress")
		with patch.object(grooming.frappe, "get_all", return_value=[]):
			with self.assertRaises(frappe.ValidationError):
				grooming.validate_grooming_appointment_completion(doc, previous)

	def test_completed_appointment_with_completed_session_is_allowed(self):
		doc = SimpleNamespace(name="PGAP-2026-00001", status="Completed")
		previous = SimpleNamespace(status="In Progress")
		with patch.object(grooming.frappe, "get_all", return_value=[{"name": "PGS-0001"}]):
			grooming.validate_grooming_appointment_completion(doc, previous)

	def test_grooming_session_final_status_keeps_shared_billing_payment_visible(self):
		script_path = Path(__file__).resolve().parents[1] / "veterinary" / "doctype" / "pet_grooming_session" / "pet_grooming_session.js"
		script = script_path.read_text()

		self.assertIn('frm.add_custom_button(__("Billing / Payment")', script)
		self.assertNotIn('frm.doc.linked_invoice && !["Draft", "Awaiting Payment", "Pending Grooming"].includes(frm.doc.status)', script)
		self.assertIn('if (!["Completed", "Cancelled"].includes(frm.doc.status))', script)


if __name__ == "__main__":
	unittest.main()
