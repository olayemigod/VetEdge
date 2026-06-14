from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import payment_gate


def consultation(linked_invoice=None):
	return frappe._dict(
		doctype="Veterinary Consultation",
		name="VCON-001",
		status="Draft",
		linked_invoice=linked_invoice,
		consultation_invoices=[],
		planned_treatments=[],
	)


def invoice(docstatus=1, outstanding_amount=0, grand_total=1000, paid_amount=0, is_pos=0):
	return frappe._dict(
		name="SINV-001",
		docstatus=docstatus,
		outstanding_amount=outstanding_amount,
		grand_total=grand_total,
		paid_amount=paid_amount,
		is_pos=is_pos,
		payments=[],
	)


class TestConsultationPaymentGate(TestCase):
	def test_default_setting_is_full_payment_required(self):
		frappe_stub = SimpleNamespace(db=SimpleNamespace(exists=Mock(return_value=False)))

		with patch.object(payment_gate, "frappe", frappe_stub):
			self.assertEqual(payment_gate.get_consultation_payment_gate(), "Full Payment Required")

	def test_billable_consultation_with_no_invoice_is_blocked(self):
		with (
			patch.object(payment_gate, "is_billable_consultation", return_value=True),
			patch.object(payment_gate, "get_consultation_invoice_names_for_gate", return_value=[]),
			patch.object(payment_gate.frappe, "throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, payment_gate.assert_consultation_can_proceed, consultation(), "In Progress")

	def test_billable_consultation_with_draft_invoice_is_blocked(self):
		with self._gate_context(invoice(docstatus=0), gate="No Payment Gate"):
			self.assertRaises(frappe.ValidationError, payment_gate.assert_consultation_can_proceed, consultation("SINV-001"), "In Progress")

	def test_full_payment_required_blocks_unpaid_invoice(self):
		with self._gate_context(invoice(docstatus=1, outstanding_amount=1000, grand_total=1000)):
			self.assertRaises(frappe.ValidationError, payment_gate.assert_consultation_can_proceed, consultation("SINV-001"), "Ready for Treatment")

	def test_full_payment_required_blocks_partially_paid_invoice(self):
		with self._gate_context(invoice(docstatus=1, outstanding_amount=500, grand_total=1000)):
			self.assertRaises(frappe.ValidationError, payment_gate.assert_consultation_can_proceed, consultation("SINV-001"), "Ready for Treatment")

	def test_full_payment_required_allows_fully_paid_invoice(self):
		with self._gate_context(invoice(docstatus=1, outstanding_amount=0, grand_total=1000)):
			payment_gate.assert_consultation_can_proceed(consultation("SINV-001"), "Ready for Treatment")

	def test_partial_payment_gate_blocks_unpaid_submitted_invoice(self):
		with self._gate_context(invoice(docstatus=1, outstanding_amount=1000, grand_total=1000), gate="Partial Payment Gate"):
			self.assertRaises(frappe.ValidationError, payment_gate.assert_consultation_can_proceed, consultation("SINV-001"), "Ready for Treatment")

	def test_partial_payment_gate_allows_partially_paid_submitted_invoice(self):
		with self._gate_context(
			invoice(docstatus=1, outstanding_amount=700, grand_total=1000),
			gate="Partial Payment Gate",
			payment_rows=[frappe._dict(parent="PE-001", allocated_amount=300)],
		):
			payment_gate.assert_consultation_can_proceed(consultation("SINV-001"), "Ready for Treatment")

	def test_partial_payment_gate_allows_fully_paid_invoice(self):
		with self._gate_context(invoice(docstatus=1, outstanding_amount=0, grand_total=1000), gate="Partial Payment Gate"):
			payment_gate.assert_consultation_can_proceed(consultation("SINV-001"), "Ready for Treatment")

	def test_no_payment_gate_allows_unpaid_submitted_invoice(self):
		with self._gate_context(invoice(docstatus=1, outstanding_amount=1000, grand_total=1000), gate="No Payment Gate") as context:
			payment_gate.assert_consultation_can_proceed(consultation("SINV-001"), "Ready for Treatment")

		context["msgprint"].assert_called_once()

	def test_no_payment_gate_still_blocks_missing_invoice(self):
		with (
			patch.object(payment_gate, "is_billable_consultation", return_value=True),
			patch.object(payment_gate, "get_consultation_invoice_names_for_gate", return_value=[]),
			patch.object(payment_gate, "get_consultation_payment_gate", return_value="No Payment Gate"),
			patch.object(payment_gate.frappe, "throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, payment_gate.assert_consultation_can_proceed, consultation(), "Ready for Treatment")

	def test_non_billable_consultation_can_proceed_without_invoice_or_payment(self):
		with patch.object(payment_gate, "is_billable_consultation", return_value=False):
			payment_gate.assert_consultation_can_proceed(consultation(), "In Progress")

	def _gate_context(self, invoice_doc, gate="Full Payment Required", payment_rows=None):
		from contextlib import contextmanager

		@contextmanager
		def manager():
			msgprint = Mock()

			def get_value(doctype, name, fieldname=None, **kwargs):
				if doctype == "Payment Entry" and fieldname == "docstatus":
					return 1
				return None

			frappe_stub = SimpleNamespace(
				db=SimpleNamespace(
					exists=lambda doctype, name=None: doctype in {"DocType", "Payment Entry Reference"},
					get_value=get_value,
				),
				get_doc=lambda doctype, name=None: invoice_doc,
				get_all=lambda doctype, **kwargs: payment_rows or [],
				throw=Mock(side_effect=frappe.ValidationError),
				msgprint=msgprint,
				ValidationError=frappe.ValidationError,
			)
			with (
				patch.object(payment_gate, "frappe", frappe_stub),
				patch.object(payment_gate, "is_billable_consultation", return_value=True),
				patch.object(payment_gate, "get_consultation_invoice_names_for_gate", return_value=["SINV-001"]),
				patch.object(payment_gate, "get_consultation_payment_gate", return_value=gate),
			):
				yield {"msgprint": msgprint}

		return manager()
