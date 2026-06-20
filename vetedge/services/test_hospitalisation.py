from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation, payment_gate


def doc(**values):
	row = frappe._dict(values)
	row.get = row.get
	row.set = lambda key, value: setattr(row, key, value)
	row.save = Mock()
	row.insert = Mock(side_effect=lambda **kwargs: setattr(row, "name", row.get("name") or "VHOS-001"))
	row.is_new = lambda: not bool(row.get("name"))
	return row


def meta(*fields):
	return SimpleNamespace(has_field=lambda fieldname: fieldname in fields)


def settings(enabled=1, gate="Partial Payment Gate"):
	return frappe._dict(
		enable_veterinary_hospitalisation=enabled,
		hospitalisation_payment_gate=gate,
	)


def invoice(docstatus=1, outstanding_amount=0, grand_total=1000, paid_amount=0, payments=None):
	return doc(
		doctype="Sales Invoice",
		name="SINV-001",
		docstatus=docstatus,
		outstanding_amount=outstanding_amount,
		grand_total=grand_total,
		paid_amount=paid_amount,
		payments=payments or [],
	)


class TestHospitalisationActions(TestCase):
	def test_feature_disabled_blocks_create_and_admit_server_side(self):
		frappe_stub = make_frappe_stub(settings_doc=settings(enabled=0))

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			self.assertRaises(
				frappe.ValidationError,
				hospitalisation.create_hospitalisation_from_consultation,
				"VCON-001",
			)
			self.assertRaises(frappe.ValidationError, hospitalisation.admit_hospitalisation, "VHOS-001")

		self.assertEqual(frappe_stub.throw.call_args.args[0], hospitalisation.DISABLED_MESSAGE)

	def test_create_hospitalisation_from_consultation_creates_linked_record(self):
		created = []
		consultation = doc(
			doctype="Veterinary Consultation",
			name="VCON-001",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
			company="Company A",
			consulting_practitioner="vet@example.com",
			presenting_complaint="Needs inpatient care",
		)

		def get_doc(doctype, name=None):
			if isinstance(doctype, dict):
				new_doc = doc(**doctype, name="VHOS-001")
				new_doc.insert = Mock(side_effect=lambda **kwargs: created.append(new_doc))
				return new_doc
			return consultation

		frappe_stub = make_frappe_stub(get_doc=get_doc, get_all=Mock(return_value=[]))
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			name = hospitalisation.create_hospitalisation_from_consultation("VCON-001")

		self.assertEqual(name, "VHOS-001")
		self.assertEqual(created[0].linked_consultation, "VCON-001")
		self.assertEqual(created[0].patient, "VP-001")
		self.assertEqual(created[0].customer, "CUST-001")
		self.assertFalse(created[0].get("care_location"))

	def test_duplicate_active_hospitalisation_from_same_consultation_is_prevented(self):
		frappe_stub = make_frappe_stub(get_all=Mock(return_value=[frappe._dict(name="VHOS-EXISTING")]))
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			name = hospitalisation.create_hospitalisation_from_consultation("VCON-001")

		self.assertEqual(name, "VHOS-EXISTING")

	def test_hospitalisation_invoice_can_be_created_and_linked(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", sales_invoice=None)
		linked_invoice = invoice(docstatus=0, outstanding_amount=1000)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: linked_invoice if doctype == "Sales Invoice" else hosp)

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(hospitalisation, "sync_hospitalisation_charges_with_billing_core", return_value={"invoice": "SINV-001"}) as sync,
		):
			name = hospitalisation.create_or_link_hospitalisation_invoice("VHOS-001")

		self.assertEqual(name, "SINV-001")
		sync.assert_called_once_with("VHOS-001")

	def test_create_hospitalisation_invoice_doc_is_deprecated(self):
		frappe_stub = make_frappe_stub()
		with patch.object(hospitalisation, "frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, hospitalisation.create_hospitalisation_invoice_doc, doc(name="VHOS-001"))

	def test_admission_blocks_without_submitted_invoice(self):
		hosp = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			status="Draft",
			customer="CUST-001",
			company="Company A",
			sales_invoice=None,
		)
		draft_invoice = invoice(docstatus=0, outstanding_amount=1000)
		session = billing_session()

		def get_doc(doctype, name=None):
			if doctype == "Sales Invoice":
				return draft_invoice
			if doctype == "Veterinary Billing Session":
				return session
			return hosp

		frappe_stub = make_frappe_stub(get_doc=get_doc)
		with billing_core_admit_context(
			frappe_stub,
			session,
			sync_result={"session": "VBS-001", "invoice": "SINV-001", "created": True},
			gate={"can_proceed": False, "status": "Blocked", "message": "At least one linked Sales Invoice must be submitted before service can proceed."},
		):
			with patch.object(hospitalisation, "create_hospitalisation_invoice_doc", side_effect=AssertionError("legacy invoice path called")):
				result = hospitalisation.admit_hospitalisation("VHOS-001")

		self.assertFalse(result["can_proceed"])
		self.assertEqual(result["billing_session"], "VBS-001")
		self.assertEqual(result["invoice"], "SINV-001")
		self.assertEqual(hosp.status, "Draft")
		self.assertEqual(hosp.payment_gate_status, "Blocked")
		self.assertEqual(hosp.sales_invoice, "SINV-001")

	def test_admit_uses_billing_core_and_allows_when_gate_passes(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", sales_invoice=None)
		paid_invoice = invoice(docstatus=1, outstanding_amount=0)
		session = billing_session(status="Paid")

		def get_doc(doctype, name=None):
			if doctype == "Sales Invoice":
				return paid_invoice
			if doctype == "Veterinary Billing Session":
				return session
			return hosp

		frappe_stub = make_frappe_stub(get_doc=get_doc)
		with billing_core_admit_context(
			frappe_stub,
			session,
			sync_result={"session": "VBS-001", "invoice": "SINV-PAID", "created": False},
			gate={"can_proceed": True, "status": "Allowed", "message": "Payment gate passed."},
		) as ctx:
			with patch.object(hospitalisation, "create_hospitalisation_invoice_doc", side_effect=AssertionError("legacy invoice path called")):
				result = hospitalisation.admit_hospitalisation("VHOS-001")

		ctx["sync"].assert_called_once_with("Veterinary Hospitalisation", "VHOS-001")
		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.status, "Admitted")
		self.assertEqual(hosp.admitted_by, "vet@example.com")
		self.assertEqual(hosp.payment_gate_status, "Allowed")

	def test_admit_no_payment_gate_allows_after_billing_core_invoice_generation(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", sales_invoice=None)
		draft_invoice = invoice(docstatus=0, outstanding_amount=1000)
		session = billing_session(payment_gate_mode="No Payment Gate")

		def get_doc(doctype, name=None):
			if doctype == "Sales Invoice":
				return draft_invoice
			if doctype == "Veterinary Billing Session":
				return session
			return hosp

		frappe_stub = make_frappe_stub(get_doc=get_doc, settings_doc=settings(gate="No Payment Gate"))
		with billing_core_admit_context(
			frappe_stub,
			session,
			sync_result={"session": "VBS-001", "invoice": "SINV-DRAFT", "created": True},
			gate={"can_proceed": True, "status": "Allowed", "message": "Invoice has been generated. Payment is not required before proceeding."},
		):
			result = hospitalisation.admit_hospitalisation("VHOS-001")

		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.status, "Admitted")
		self.assertEqual(hosp.sales_invoice, "SINV-DRAFT")

	def test_draft_invoice_does_not_satisfy_any_gate(self):
		for gate in ("Full Payment Required", "Partial Payment Gate", "No Payment Gate"):
			with self.subTest(gate=gate):
				hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", sales_invoice="SINV-001")
				draft_invoice = invoice(docstatus=0, outstanding_amount=1000)
				frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: draft_invoice if doctype == "Sales Invoice" else hosp, settings_doc=settings(gate=gate))
				with hospitalisation_gate_context(frappe_stub, draft_invoice, gate=gate):
					result = hospitalisation.check_hospitalisation_payment_gate("VHOS-001")

				self.assertFalse(result["can_proceed"])
				self.assertEqual(hosp.payment_gate_status, "Blocked")

	def test_full_payment_required_blocks_unpaid_invoice(self):
		result, hosp = run_hospitalisation_gate("Full Payment Required", invoice(docstatus=1, outstanding_amount=1000))

		self.assertFalse(result["can_proceed"])
		self.assertEqual(hosp.payment_gate_status, "Blocked")

	def test_partial_payment_gate_allows_partially_paid_invoice(self):
		result, hosp = run_hospitalisation_gate(
			"Partial Payment Gate",
			invoice(docstatus=1, outstanding_amount=700, grand_total=1000),
			payment_rows=[frappe._dict(parent="PE-001", allocated_amount=300)],
		)

		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.payment_gate_status, "Allowed")

	def test_no_payment_gate_allows_submitted_unpaid_invoice(self):
		result, hosp = run_hospitalisation_gate("No Payment Gate", invoice(docstatus=1, outstanding_amount=1000))

		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.payment_gate_status, "Allowed")

	def test_hospitalisation_title_includes_patient_date_and_admitting_vet(self):
		hosp = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			patient="VP-001",
			admission_datetime="2026-06-20 09:30:00",
			attending_veterinarian="vet@example.com",
		)
		frappe_stub = make_frappe_stub()
		frappe_stub.db.get_value.side_effect = lambda doctype, name, fieldname=None, **kwargs: {
			("Veterinary Patient", "VP-001", "patient_name"): "Max",
			("User", "vet@example.com", "full_name"): "Dr Ada Bello",
		}.get((doctype, name, fieldname))

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "formatdate", return_value="20 Jun 2026"),
		):
			hospitalisation.sync_hospitalisation_title(hosp)

		self.assertEqual(hosp.hospitalisation_title, "Max - 20 Jun 2026 - Dr Ada Bello - Hospitalisation")

	def test_discharge_sets_discharge_fields(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Under Care")
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: hosp)
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(hospitalisation, "now", return_value="2026-06-19 09:00:00"),
		):
			name = hospitalisation.discharge_hospitalisation("VHOS-001", "Recovered")

		self.assertEqual(name, "VHOS-001")
		self.assertEqual(hosp.status, "Discharged")
		self.assertEqual(hosp.discharged_by, "vet@example.com")
		self.assertEqual(hosp.discharge_summary, "Recovered")


def run_hospitalisation_gate(gate, invoice_doc, payment_rows=None):
	hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", sales_invoice="SINV-001")
	frappe_stub = make_frappe_stub(
		get_doc=lambda doctype, name=None: invoice_doc if doctype == "Sales Invoice" else hosp,
		settings_doc=settings(gate=gate),
	)
	with hospitalisation_gate_context(frappe_stub, invoice_doc, gate=gate, payment_rows=payment_rows):
		result = hospitalisation.check_hospitalisation_payment_gate("VHOS-001")
	return result, hosp


def hospitalisation_gate_context(frappe_stub, invoice_doc, gate="Partial Payment Gate", payment_rows=None):
	from contextlib import contextmanager

	@contextmanager
	def manager():
		payment_frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda doctype, name=None: True,
				get_value=lambda doctype, name, fieldname=None, **kwargs: 1 if doctype == "Payment Entry" else None,
			),
			get_doc=lambda doctype, name=None: invoice_doc,
			get_all=lambda doctype, **kwargs: payment_rows or [],
			throw=Mock(side_effect=frappe.ValidationError),
			msgprint=Mock(),
			ValidationError=frappe.ValidationError,
		)
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(payment_gate, "frappe", payment_frappe_stub),
		):
			yield

	return manager()


def billing_session(**values):
	defaults = {
		"doctype": "Veterinary Billing Session",
		"name": "VBS-001",
		"status": "Active",
		"payment_gate_mode": "Partial Payment Gate",
		"charges": [],
	}
	defaults.update(values)
	session = frappe._dict(defaults)
	session.save = Mock()
	return session


def billing_core_admit_context(frappe_stub, session, sync_result=None, gate=None):
	from contextlib import contextmanager

	@contextmanager
	def manager():
		sync_result = manager.sync_result or {"session": session.name, "invoice": "SINV-001", "created": True}
		gate_result = manager.gate or {"can_proceed": False, "status": "Blocked", "message": "Blocked"}
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value=sync_result) as sync,
			patch("vetedge.services.billing_core.get_payment_gate_status", return_value=gate_result),
			patch("vetedge.services.billing_core.get_billing_session_summary", return_value={"name": session.name, "payment_gate": gate_result}),
		):
			yield {"sync": sync}

	manager.sync_result = sync_result
	manager.gate = gate
	return manager()


def make_frappe_stub(get_doc=None, get_all=None, settings_doc=None, item_exists=True):
	settings_doc = settings_doc or settings()
	get_doc = get_doc or (lambda doctype, name=None: doc(doctype=doctype, name=name))
	get_all = get_all or Mock(return_value=[])

	def exists(doctype, name=None):
		if doctype == "Item":
			return item_exists
		return True

	return SimpleNamespace(
		db=SimpleNamespace(exists=exists, get_value=Mock(return_value=None)),
		get_meta=lambda doctype: meta(
			"enable_veterinary_hospitalisation",
			"hospitalisation_payment_gate",
			"branch",
		),
		get_single=lambda doctype: settings_doc,
		get_doc=get_doc,
		get_all=get_all,
		throw=Mock(side_effect=frappe.ValidationError),
		session=SimpleNamespace(user="vet@example.com"),
		ValidationError=frappe.ValidationError,
	)
