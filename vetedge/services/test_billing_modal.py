from __future__ import annotations

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

	def test_submit_modal_invoice_submits_draft_invoice(self):
		source = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			linked_invoice="SINV-001",
			service_branch="Main",
		)
		invoice = make_invoice(docstatus=0)

		with modal_action_context(source, invoice):
			result = billing_modal.submit_modal_invoice("Veterinary Consultation", "VCON-001")

		self.assertEqual(result["invoice"], "SINV-001")
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


def make_invoice(docstatus=1, outstanding_amount=1000):
	return frappe._dict(
		doctype="Sales Invoice",
		name="SINV-001",
		docstatus=docstatus,
		status="Draft" if docstatus == 0 else "Unpaid",
		customer="CUST-001",
		branch="Main",
		grand_total=1000,
		paid_amount=0,
		outstanding_amount=outstanding_amount,
		currency="NGN",
		submit=Mock(),
	)


def make_payment_entry():
	return frappe._dict(
		doctype="Payment Entry",
		name="PE-001",
		paid_amount=0,
		received_amount=0,
		references=[frappe._dict(reference_doctype="Sales Invoice", reference_name="SINV-001", allocated_amount=0)],
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
			patch.object(billing_modal, "submitted_payment_exists", return_value=False),
		]
		for patcher in self.patches:
			patcher.start()
		return self

	def __exit__(self, exc_type, exc, tb):
		for patcher in reversed(self.patches):
			patcher.stop()
		return False
