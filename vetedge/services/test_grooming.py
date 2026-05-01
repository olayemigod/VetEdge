from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

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


if __name__ == "__main__":
	unittest.main()
