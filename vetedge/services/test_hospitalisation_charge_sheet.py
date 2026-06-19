from __future__ import annotations

from contextlib import ExitStack
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation


def activity(**values):
	defaults = {
		"name": "ACT-001",
		"idx": 1,
		"activity_type": "Medication",
		"clinical_notes": "Dose given",
		"billable": 1,
		"billing_status": "Pending Charge",
		"item": "ITEM-001",
		"qty": 2,
		"uom": "Nos",
	}
	defaults.update(values)
	return frappe._dict(defaults)


def hospitalisation_doc(**values):
	defaults = {
		"doctype": "Veterinary Hospitalisation",
		"name": "VHOS-001",
		"status": "Under Care",
		"customer": "CUST-001",
		"company": "Company A",
		"service_branch": "Main",
		"sales_invoice": None,
		"invoice_status": "Not Invoiced",
		"payment_gate_status": "Blocked",
		"payment_gate_message": "Still blocked",
		"activities": [],
		"charge_items": [],
	}
	defaults.update(values)
	doc = frappe._dict(defaults)
	doc.save = Mock()
	doc.append = lambda fieldname, row: doc.setdefault(fieldname, []).append(frappe._dict(row)) or doc[fieldname][-1]
	return doc


def invoice_doc(name="SINV-001", docstatus=0, items=None):
	invoice = frappe._dict(
		doctype="Sales Invoice",
		name=name,
		docstatus=docstatus,
		outstanding_amount=0 if docstatus == 0 else 100,
		grand_total=100,
		items=items or [],
	)
	invoice.save = Mock()
	invoice.insert = Mock()
	invoice.append = lambda fieldname, row: invoice.setdefault(fieldname, []).append(frappe._dict(row)) or invoice[fieldname][-1]
	return invoice


class TestHospitalisationChargeSheet(TestCase):
	def test_clinical_only_activity_does_not_create_charge_item(self):
		hosp = hospitalisation_doc(activities=[activity(name="ACT-1", billable=0, item=None, activity_type="Nursing Note")])

		with charge_context(hosp):
			result = hospitalisation.build_hospitalisation_charge_items("VHOS-001")

		self.assertEqual(result["created"], 0)
		self.assertEqual(result["skipped"][0]["reason"], "not_billable")
		self.assertEqual(hosp.charge_items, [])

	def test_billable_activity_without_item_is_skipped(self):
		hosp = hospitalisation_doc(activities=[activity(name="ACT-1", billable=1, item=None)])

		with charge_context(hosp):
			result = hospitalisation.build_hospitalisation_charge_items("VHOS-001")

		self.assertEqual(result["created"], 0)
		self.assertEqual(result["skipped"][0]["reason"], "missing_item")

	def test_billable_activity_with_item_creates_one_charge_item(self):
		hosp = hospitalisation_doc(activities=[activity(name="ACT-1", item="ITEM-001", qty=2)])

		with charge_context(hosp):
			result = hospitalisation.build_hospitalisation_charge_items("VHOS-001")

		self.assertEqual(result["created"], 1)
		self.assertEqual(len(hosp.charge_items), 1)
		self.assertEqual(hosp.charge_items[0].item, "ITEM-001")
		self.assertEqual(hosp.charge_items[0].amount, 20)
		self.assertEqual(hosp.activities[0].billing_status, "Pending Charge")

	def test_build_charge_items_is_idempotent(self):
		hosp = hospitalisation_doc(activities=[activity(name="ACT-1", item="ITEM-001")])

		with charge_context(hosp):
			first = hospitalisation.build_hospitalisation_charge_items("VHOS-001")
			second = hospitalisation.build_hospitalisation_charge_items("VHOS-001")

		self.assertEqual(first["created"], 1)
		self.assertEqual(second["created"], 0)
		self.assertEqual(second["existing"], 1)
		self.assertEqual(len(hosp.charge_items), 1)

	def test_draft_invoice_receives_pending_charge_items(self):
		charge = make_charge("VHOS-001:ACT-1")
		hosp = hospitalisation_doc(sales_invoice="SINV-001", charge_items=[charge], activities=[activity(name="ACT-1")])
		invoice = invoice_doc(docstatus=0)

		with charge_context(hosp, invoice):
			result = hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")

		self.assertEqual(result["invoice"], "SINV-001")
		self.assertEqual(result["added_count"], 1)
		self.assertEqual(len(invoice.get("items")), 1)
		self.assertEqual(charge.billing_status, "Invoiced")
		self.assertEqual(hosp.activities[0].billing_status, "Charged")

	def test_sync_is_idempotent_for_invoice_items(self):
		charge = make_charge("VHOS-001:ACT-1")
		hosp = hospitalisation_doc(sales_invoice="SINV-001", charge_items=[charge], activities=[activity(name="ACT-1")])
		invoice = invoice_doc(docstatus=0)

		with charge_context(hosp, invoice):
			first = hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")
			second = hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")

		self.assertEqual(first["added_count"], 1)
		self.assertEqual(second["added_count"], 0)
		self.assertEqual(len(invoice.get("items")), 1)

	def test_submitted_linked_invoice_is_not_mutated(self):
		charge = make_charge("VHOS-001:ACT-1")
		old_invoice = invoice_doc(name="SINV-SUB", docstatus=1, items=[])
		new_invoice = invoice_doc(name="SINV-NEW", docstatus=0, items=[])
		hosp = hospitalisation_doc(sales_invoice="SINV-SUB", charge_items=[charge], activities=[activity(name="ACT-1")])

		with charge_context(hosp, old_invoice, created_invoice=new_invoice):
			result = hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")

		self.assertTrue(result["created_new_invoice"])
		self.assertEqual(result["invoice"], "SINV-NEW")
		self.assertEqual(old_invoice.get("items"), [])
		old_invoice.save.assert_not_called()
		self.assertEqual(len(new_invoice.get("items")), 1)

	def test_cancelled_linked_invoice_is_not_reused(self):
		charge = make_charge("VHOS-001:ACT-1")
		cancelled_invoice = invoice_doc(name="SINV-CAN", docstatus=2, items=[])
		new_invoice = invoice_doc(name="SINV-NEW", docstatus=0, items=[])
		hosp = hospitalisation_doc(sales_invoice="SINV-CAN", charge_items=[charge], activities=[activity(name="ACT-1")])

		with charge_context(hosp, cancelled_invoice, created_invoice=new_invoice):
			result = hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")

		self.assertTrue(result["created_new_invoice"])
		self.assertEqual(hosp.sales_invoice, "SINV-NEW")
		self.assertEqual(cancelled_invoice.get("items"), [])

	def test_vaccination_billable_activity_creates_charge_without_status_change(self):
		hosp = hospitalisation_doc(status="Under Care", activities=[activity(name="ACT-VAX", activity_type="Vaccination")])

		with charge_context(hosp):
			hospitalisation.build_hospitalisation_charge_items("VHOS-001")

		self.assertEqual(len(hosp.charge_items), 1)
		self.assertEqual(hosp.charge_items[0].activity_type, "Vaccination")
		self.assertEqual(hosp.status, "Under Care")

	def test_sync_does_not_change_payment_gate_status_to_allowed(self):
		charge = make_charge("VHOS-001:ACT-1")
		hosp = hospitalisation_doc(
			sales_invoice="SINV-001",
			payment_gate_status="Blocked",
			payment_gate_message="Blocked before sync",
			charge_items=[charge],
			activities=[activity(name="ACT-1")],
		)
		invoice = invoice_doc(docstatus=0)

		with charge_context(hosp, invoice):
			hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")

		self.assertEqual(hosp.payment_gate_status, "Blocked")
		self.assertEqual(hosp.payment_gate_message, "Blocked before sync")

	def test_sync_uses_billing_core_active_draft_invoice(self):
		charge = make_charge("VHOS-001:ACT-1")
		hosp = hospitalisation_doc(
			status="Under Care",
			sales_invoice=None,
			payment_gate_status="Blocked",
			payment_gate_message="Still blocked",
			charge_items=[charge],
			activities=[activity(name="ACT-1")],
		)
		invoice = invoice_doc(name="SINV-REG", docstatus=0, items=[])
		session = frappe._dict(
			name="VBS-REG",
			charges=[
				frappe._dict(
					source_doctype="Veterinary Hospitalisation",
					source_name="VHOS-001",
					charge_key="Veterinary Hospitalisation:VHOS-001:Hospitalisation:VHOS-001:ACT-1",
					invoice="SINV-REG",
					invoice_item_name="SII-001",
					billing_status="Draft Invoiced",
				)
			],
		)

		with billing_core_charge_context(hosp, invoice, session):
			result = hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")

		self.assertEqual(result["invoice"], "SINV-REG")
		self.assertEqual(result["billing_session"], "VBS-REG")
		self.assertEqual(hosp.sales_invoice, "SINV-REG")
		self.assertEqual(charge.billing_status, "Invoiced")
		self.assertEqual(charge.sales_invoice, "SINV-REG")
		self.assertEqual(hosp.activities[0].billing_status, "Charged")
		self.assertEqual(hosp.status, "Under Care")
		self.assertEqual(hosp.payment_gate_status, "Blocked")
		self.assertEqual(hosp.payment_gate_message, "Still blocked")

	def test_billing_core_sync_does_not_duplicate_local_invoiced_charge(self):
		charge = make_charge("VHOS-001:ACT-1")
		charge.billing_status = "Invoiced"
		charge.sales_invoice = "SINV-REG"
		hosp = hospitalisation_doc(sales_invoice="SINV-REG", charge_items=[charge], activities=[activity(name="ACT-1", billing_status="Charged")])
		invoice = invoice_doc(name="SINV-REG", docstatus=0, items=[frappe._dict(description="Medication\nVetEdge billing charge: Veterinary Hospitalisation:VHOS-001:Hospitalisation:VHOS-001:ACT-1")])
		session = frappe._dict(name="VBS-REG", charges=[])

		with billing_core_charge_context(hosp, invoice, session, added_count=0):
			result = hospitalisation.sync_hospitalisation_charges_to_invoice("VHOS-001")

		self.assertEqual(result["added_count"], 0)
		self.assertEqual(len(invoice.get("items")), 1)
		self.assertEqual(charge.billing_status, "Invoiced")


def make_charge(source_hash):
	return frappe._dict(
		source_activity=source_hash.split(":", 1)[1],
		activity_type="Medication",
		item="ITEM-001",
		description="Medication - Dose given",
		qty=1,
		uom="Nos",
		rate=10,
		amount=10,
		billing_status="Pending Invoice",
		source_hash=source_hash,
	)


class charge_context:
	def __init__(self, hosp, linked_invoice=None, created_invoice=None):
		self.hosp = hosp
		self.linked_invoice = linked_invoice or invoice_doc(name=hosp.get("sales_invoice") or "SINV-001", docstatus=0)
		self.created_invoice = created_invoice or invoice_doc(name="SINV-NEW", docstatus=0)
		self.stack = ExitStack()

	def __enter__(self):
		linked_invoice = self.linked_invoice
		created_invoice = self.created_invoice
		hosp = self.hosp

		def exists(doctype, name=None):
			if doctype in {"DocType", "Item"}:
				return True
			if doctype == "Sales Invoice":
				return bool(name)
			return True

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Item" and fieldname == "item_name":
				return "Test Item"
			if doctype == "Item" and fieldname == "stock_uom":
				return "Nos"
			if doctype == "Item" and fieldname == "standard_rate":
				return 10
			return None

		def get_doc(doctype, name=None):
			if isinstance(doctype, dict):
				created_invoice.update(doctype)
				created_invoice.name = created_invoice.name or "SINV-NEW"
				return created_invoice
			if doctype == "Veterinary Hospitalisation":
				return hosp
			if doctype == "Sales Invoice":
				return linked_invoice if name == linked_invoice.name else created_invoice
			return frappe._dict(name=name)

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=get_value),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname in {"enable_veterinary_hospitalisation"}),
			get_single=lambda doctype: frappe._dict(enable_veterinary_hospitalisation=1),
			get_doc=get_doc,
			_dict=frappe._dict,
			session=SimpleNamespace(user="vet@example.com"),
			ValidationError=frappe.ValidationError,
			throw=Mock(side_effect=frappe.ValidationError),
		)
		self.stack.enter_context(
			patch.multiple(
				hospitalisation,
				frappe=frappe_stub,
				require_internal_user=Mock(),
				nowdate=Mock(return_value="2026-06-19"),
			)
		)
		self.stack.enter_context(patch("vetedge.services.billing_core.is_billing_sessions_enabled", return_value=False))
		return self

	def __exit__(self, exc_type, exc, tb):
		return self.stack.__exit__(exc_type, exc, tb)


class billing_core_charge_context:
	def __init__(self, hosp, invoice, session, added_count=1, created=False):
		self.hosp = hosp
		self.invoice = invoice
		self.session = session
		self.added_count = added_count
		self.created = created
		self.stack = ExitStack()

	def __enter__(self):
		hosp = self.hosp
		invoice = self.invoice
		session = self.session

		def exists(doctype, name=None):
			if doctype in {"DocType", "Item", "Veterinary Billing Session"}:
				return True
			if doctype == "Sales Invoice":
				return bool(name)
			return True

		def get_doc(doctype, name=None):
			if doctype == "Veterinary Hospitalisation":
				return hosp
			if doctype == "Sales Invoice":
				return invoice
			if doctype == "Veterinary Billing Session":
				return session
			return frappe._dict(name=name)

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=Mock(return_value=None)),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname in {"enable_veterinary_hospitalisation"}),
			get_single=lambda doctype: frappe._dict(enable_veterinary_hospitalisation=1),
			get_doc=get_doc,
			_dict=frappe._dict,
			session=SimpleNamespace(user="vet@example.com"),
			ValidationError=frappe.ValidationError,
			throw=Mock(side_effect=frappe.ValidationError),
		)
		self.stack.enter_context(
			patch.multiple(
				hospitalisation,
				frappe=frappe_stub,
				require_internal_user=Mock(),
				get_invoice_payment_status=Mock(return_value="Draft"),
			)
		)
		self.stack.enter_context(patch("vetedge.services.billing_core.is_billing_sessions_enabled", return_value=True))
		self.stack.enter_context(
			patch(
				"vetedge.services.billing_core.sync_source_to_billing_session",
				return_value={
					"invoice": invoice.name,
					"session": session.name,
					"created": self.created,
					"added_count": self.added_count,
				},
			)
		)
		return self

	def __exit__(self, exc_type, exc, tb):
		return self.stack.__exit__(exc_type, exc, tb)
