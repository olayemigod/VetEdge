from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import billing, billing_core, billing_modal, boarding, grooming, lab, registration_billing, vaccination


def make_session(**values):
	defaults = {
		"doctype": billing_core.BILLING_SESSION_DOCTYPE,
		"name": "VBS-001",
		"customer": "CUST-001",
		"animal": "PAT-001",
		"company": "Company A",
		"branch": "Main",
		"status": "Active",
		"payment_gate_mode": "Full Payment Gate",
		"current_draft_invoice": None,
		"latest_invoice": None,
		"total_charges": 0,
		"total_invoiced": 0,
		"total_paid": 0,
		"outstanding_amount": 0,
		"payment_status": "Not Invoiced",
		"charges": [],
	}
	defaults.update(values)
	session = frappe._dict(defaults)
	session.append = lambda fieldname, row: session.setdefault(fieldname, []).append(frappe._dict(row)) or session[fieldname][-1]
	session.save = Mock()
	return session


def make_invoice(name="SINV-001", docstatus=0, items=None, outstanding_amount=100):
	invoice = frappe._dict(
		doctype="Sales Invoice",
		name=name,
		docstatus=docstatus,
		status="Draft" if docstatus == 0 else "Unpaid",
		customer="CUST-001",
		company="Company A",
		branch="Main",
		grand_total=100,
		paid_amount=0,
		outstanding_amount=outstanding_amount,
		currency="NGN",
		items=items or [],
	)
	invoice.append = lambda fieldname, row: invoice.setdefault(fieldname, []).append(frappe._dict(row)) or invoice[fieldname][-1]
	invoice.insert = Mock()
	invoice.save = Mock()
	return invoice


def charge_payload(key="consultation-fee", item="ITEM-001", amount=100):
	return {
		"source_doctype": "Veterinary Consultation",
		"source_name": "VCON-001",
		"source_detail_name": key,
		"charge_key": key,
		"item_code": item,
		"item_name": item,
		"description": "Charge",
		"qty": 1,
		"rate": amount,
		"amount": amount,
		"cost_center": "CC-Main",
		"branch": "Main",
	}


class TestBillingCore(TestCase):
	def test_add_or_update_session_charge_is_idempotent(self):
		session = make_session()

		first = billing_core.add_or_update_session_charge(session, charge_payload())
		second = billing_core.add_or_update_session_charge(session, charge_payload(amount=125))

		self.assertIs(first, second)
		self.assertEqual(len(session.charges), 1)
		self.assertEqual(session.charges[0].amount, 125)

	def test_submitted_charge_is_not_mutated_by_charge_sync(self):
		session = make_session(charges=[frappe._dict({**charge_payload(), "billing_status": "Submitted Invoiced", "amount": 100})])

		row = billing_core.add_or_update_session_charge(session, charge_payload(amount=250))

		self.assertEqual(row.amount, 100)
		self.assertEqual(row.billing_status, "Submitted Invoiced")

	def test_invoice_sync_does_not_duplicate_invoice_items(self):
		session = make_session(current_draft_invoice="SINV-001", charges=[])
		billing_core.add_or_update_session_charge(session, charge_payload())
		invoice = make_invoice(items=[frappe._dict({"description": "Charge\nVetEdge billing charge: consultation-fee"})])

		with billing_core_context(session, invoice):
			result = billing_core.sync_session_charges_to_invoice(session)

		self.assertEqual(result["added_count"], 0)
		self.assertEqual(result["updated_count"], 1)
		self.assertEqual(len(invoice.get("items")), 1)

	def test_submitted_current_invoice_creates_new_draft_for_new_charge(self):
		session = make_session(current_draft_invoice="SINV-SUB", latest_invoice="SINV-SUB")
		submitted = make_invoice("SINV-SUB", docstatus=1)
		new_invoice = make_invoice("SINV-NEW", docstatus=0)

		with billing_core_context(session, submitted, created_invoice=new_invoice):
			invoice, created = billing_core.create_or_update_draft_invoice_for_session(session)

		self.assertTrue(created)
		self.assertEqual(invoice.name, "SINV-NEW")
		self.assertEqual(session.current_draft_invoice, "SINV-NEW")

	def test_cancelled_current_invoice_creates_new_draft_for_new_charge(self):
		session = make_session(current_draft_invoice="SINV-CAN", latest_invoice="SINV-CAN")
		cancelled = make_invoice("SINV-CAN", docstatus=2)
		new_invoice = make_invoice("SINV-NEW", docstatus=0)

		with billing_core_context(session, cancelled, created_invoice=new_invoice):
			invoice, created = billing_core.create_or_update_draft_invoice_for_session(session)

		self.assertTrue(created)
		self.assertEqual(invoice.name, "SINV-NEW")

	def test_no_payment_gate_allows_after_invoice_generation(self):
		session = make_session(payment_gate_mode="No Payment Gate", current_draft_invoice="SINV-001", latest_invoice="SINV-001")
		invoice = make_invoice(docstatus=0)

		with billing_core_context(session, invoice):
			status = billing_core.get_payment_gate_status(session)

		self.assertTrue(status["can_proceed"])

	def test_partial_payment_gate_requires_paid_amount_across_session(self):
		session = make_session(payment_gate_mode="Partial Payment Gate", latest_invoice="SINV-001", total_paid=0)
		invoice = make_invoice(docstatus=1, outstanding_amount=100)

		with billing_core_context(session, invoice, paid_amount=0):
			blocked = billing_core.get_payment_gate_status(session)
		with billing_core_context(session, invoice, paid_amount=25):
			allowed = billing_core.get_payment_gate_status(session)

		self.assertFalse(blocked["can_proceed"])
		self.assertTrue(allowed["can_proceed"])

	def test_full_payment_gate_requires_zero_session_outstanding(self):
		session = make_session(payment_gate_mode="Full Payment Gate", latest_invoice="SINV-001")
		invoice = make_invoice(docstatus=1, outstanding_amount=100)

		with billing_core_context(session, invoice, paid_amount=0):
			blocked = billing_core.get_payment_gate_status(session)
		invoice.outstanding_amount = 0
		with billing_core_context(session, invoice, paid_amount=100):
			allowed = billing_core.get_payment_gate_status(session)

		self.assertFalse(blocked["can_proceed"])
		self.assertTrue(allowed["can_proceed"])

	def test_modal_summary_returns_session_payment_gate(self):
		summary = {"name": "VBS-001", "payment_gate": {"can_proceed": True}, "invoices": []}
		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal, "get_billing_source_config", return_value=billing_modal.BILLING_SOURCE_CONFIGS["Veterinary Consultation"]),
			patch.object(billing_modal.frappe, "get_doc", return_value=frappe._dict(doctype="Veterinary Consultation", name="VCON-001", linked_invoice=None)),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_billing_session_summary_for_source", return_value=summary),
			patch.object(billing_modal, "get_payment_modes", return_value=[]),
		):
			state = billing_modal.get_billing_modal_state("Veterinary Consultation", "VCON-001")

		self.assertEqual(state["billing_session"], summary)
		self.assertTrue(state["payment_gate"]["can_proceed"])



	def test_global_billing_sources_are_modal_session_supported(self):
		for doctype in [
			"Veterinary Consultation",
			"Veterinary Lab Order",
			"Veterinary Vaccination Record",
			"Veterinary Hospitalisation",
			"Veterinary Patient",
			"Pet Grooming Session",
			"Pet Boarding Booking",
		]:
			self.assertTrue(billing_modal.source_supports_billing_session(doctype), doctype)

	def test_consultation_invoice_api_uses_billing_core(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", service_branch="Main", status="Draft")
		doc.save = Mock()
		settings = billing.ConsultationBillingSettings(True, "CONS-ITEM", False, False, False, True)
		with (
			patch.object(billing, "require_internal_user"),
			patch.object(billing, "can_access_consultation"),
			patch.object(billing, "get_consultation_billing_settings", return_value=settings),
			patch.object(billing, "validate_consultation_invoice_request"),
			patch.object(billing, "use_billing_core_for_source", return_value=True),
			patch.object(billing.frappe, "get_doc", side_effect=lambda doctype, name=None: doc if doctype == "Veterinary Consultation" else make_invoice(name or "SINV-001")),
			patch.object(billing.frappe.db, "get_value", return_value="Draft"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001", "created": True}) as sync,
		):
			result = billing.create_consultation_invoice("VCON-001")

		sync.assert_called_once_with("Veterinary Consultation", "VCON-001")
		self.assertEqual(result["billing_session"], "VBS-001")

	def test_lab_order_invoice_api_uses_billing_core(self):
		order = frappe._dict(doctype="Veterinary Lab Order", name="VLAB-001", linked_invoice=None)
		with (
			patch.object(lab, "require_internal_user"),
			patch.object(lab, "can_access_lab_order"),
			patch.object(lab, "get_current_user", return_value="vet@example.com"),
			patch.object(lab, "use_billing_core_for_lab_order", return_value=True),
			patch.object(lab.frappe, "get_doc", return_value=order),
			patch.object(lab.frappe.db, "set_value") as set_value,
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001", "created": True}) as sync,
		):
			result = lab.create_lab_order_invoice("VLAB-001")

		sync.assert_called_once_with(lab.LAB_ORDER_DOCTYPE, "VLAB-001")
		set_value.assert_called_once()
		self.assertEqual(result["billing_session"], "VBS-001")

	def test_vaccination_invoice_api_uses_billing_core(self):
		doc = frappe._dict(doctype="Veterinary Vaccination Record", name="VVAC-001", status="Draft", linked_invoice=None)
		doc.save = Mock()
		with (
			patch.object(vaccination, "require_internal_user"),
			patch.object(vaccination.frappe, "get_doc", return_value=doc),
			patch.object(vaccination, "use_billing_core_for_vaccination", return_value=True),
			patch.object(vaccination, "get_vaccination_workflow_status", return_value="Awaiting Payment"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001"}) as sync,
		):
			result = vaccination.create_or_update_vaccination_invoice("VVAC-001")

		sync.assert_called_once_with(vaccination.VACCINATION_RECORD_DOCTYPE, "VVAC-001")
		self.assertEqual(result["billing_session"], "VBS-001")
		self.assertEqual(doc.linked_invoice, "SINV-001")

	def test_registration_invoice_uses_billing_core(self):
		doc = frappe._dict(doctype="Veterinary Patient", name="PAT-001")
		rule = registration_billing.RegistrationBillingRule(True, "Main", "REG-ITEM", 100, True, True)
		with (
			patch.object(registration_billing, "use_billing_core_for_registration", return_value=True),
			patch.object(registration_billing.frappe, "get_doc", return_value=make_invoice("SINV-001")),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001"}) as sync,
		):
			invoice = registration_billing.create_registration_invoice(doc, rule)

		sync.assert_called_once_with("Veterinary Patient", "PAT-001")
		self.assertEqual(invoice.name, "SINV-001")

	def test_grooming_invoice_uses_billing_core(self):
		doc = frappe._dict(doctype="Pet Grooming Session", name="PGS-001", status="Draft", grooming_service="Bath")
		with (
			patch.object(grooming, "is_grooming_billing_enabled", return_value=True),
			patch.object(grooming, "use_billing_core_for_grooming", return_value=True),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "created": True, "session": "VBS-001"}) as sync,
		):
			invoice, created = grooming.create_grooming_invoice(doc)

		sync.assert_called_once_with(grooming.GROOMING_SESSION_DOCTYPE, "PGS-001")
		self.assertEqual(invoice, "SINV-001")
		self.assertTrue(created)

	def test_boarding_invoice_uses_billing_core(self):
		doc = frappe._dict(doctype="Pet Boarding Booking", name="PBB-001", status="Reserved")
		doc.save = Mock()
		with (
			patch.object(boarding, "use_billing_core_for_boarding", return_value=True),
			patch.object(boarding, "sync_boarding_charge_fields"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "created": True, "session": "VBS-001"}) as sync,
		):
			result = boarding.create_boarding_invoice_doc(doc)

		sync.assert_called_once_with(boarding.PET_BOARDING_BOOKING_DOCTYPE, "PBB-001")
		self.assertEqual(result["billing_session"], "VBS-001")
		self.assertEqual(doc.linked_invoice, "SINV-001")

	def test_adapter_dispatch_includes_grooming_and_boarding(self):
		with (
			patch.object(billing_core, "get_grooming_charge_payloads", return_value=[{"charge_key": "groom"}]) as grooming_payloads,
			patch.object(billing_core, "get_boarding_charge_payloads", return_value=[{"charge_key": "board"}]) as boarding_payloads,
		):
			self.assertEqual(billing_core.get_source_charge_payloads("Pet Grooming Session", "PGS-001")[0]["charge_key"], "groom")
			self.assertEqual(billing_core.get_source_charge_payloads("Pet Boarding Booking", "PBB-001")[0]["charge_key"], "board")

		grooming_payloads.assert_called_once_with("PGS-001", None)
		boarding_payloads.assert_called_once_with("PBB-001", None)

	def test_related_sources_join_consultation_session_context(self):
		with patch.object(billing_core.frappe.db, "get_value", side_effect=lambda doctype, name, fieldname=None, **kwargs: "VCON-001" if fieldname in {"consultation", "linked_consultation"} else None):
			self.assertEqual(billing_core.get_source_context("Veterinary Lab Order", "VLAB-001"), ("Veterinary Consultation", "VCON-001"))
			self.assertEqual(billing_core.get_source_context("Veterinary Vaccination Record", "VVAC-001"), ("Veterinary Consultation", "VCON-001"))

	def test_billing_core_does_not_introduce_ignore_permissions(self):
		from pathlib import Path

		source = Path(billing_core.__file__).read_text()
		self.assertNotIn("ignore_permissions=True", source)


class billing_core_context:
	def __init__(self, session, linked_invoice, created_invoice=None, paid_amount=0):
		self.session = session
		self.linked_invoice = linked_invoice
		self.created_invoice = created_invoice or make_invoice("SINV-NEW")
		self.paid_amount = paid_amount
		self.patches = []

	def __enter__(self):
		def exists(doctype, name=None):
			if doctype in {"DocType", "Veterinary Settings"}:
				return True
			if doctype == "Sales Invoice":
				return bool(name)
			return True

		def get_doc(doctype, name=None):
			if isinstance(doctype, dict):
				self.created_invoice.update(doctype)
				return self.created_invoice
			if doctype == billing_core.BILLING_SESSION_DOCTYPE:
				return self.session
			if doctype == "Sales Invoice":
				if name == self.linked_invoice.name:
					return self.linked_invoice
				return self.created_invoice
			return frappe._dict(name=name)

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Sales Invoice" and fieldname == "docstatus":
				if name == self.linked_invoice.name:
					return self.linked_invoice.docstatus
				return self.created_invoice.docstatus
			return None

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=get_value),
			get_doc=get_doc,
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: False),
			get_single=lambda doctype: frappe._dict(enable_billing_sessions=1),
			get_all=Mock(return_value=[]),
			_dict=frappe._dict,
			ValidationError=frappe.ValidationError,
			throw=Mock(side_effect=frappe.ValidationError),
		)
		self.patches = [
			patch.object(billing_core, "frappe", frappe_stub),
			patch.object(billing_core, "get_default_company", return_value="Company A"),
			patch.object(billing_core, "get_billing_cost_center", return_value="CC-Main"),
			patch.object(
				billing_core,
				"get_invoice_payment_state",
				side_effect=lambda invoice: {
					"invoice": invoice,
					"paid_amount": self.paid_amount,
					"outstanding_amount": self.linked_invoice.outstanding_amount if invoice == self.linked_invoice.name else self.created_invoice.outstanding_amount,
					"has_payment": self.paid_amount > 0,
					"is_fully_paid": (self.linked_invoice.outstanding_amount if invoice == self.linked_invoice.name else self.created_invoice.outstanding_amount) <= 0,
				},
			),
		]
		for patcher in self.patches:
			patcher.start()
		return self

	def __exit__(self, exc_type, exc, tb):
		for patcher in reversed(self.patches):
			patcher.stop()
		return False
