from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services.consultation_billing_plan import (
	sync_lab_order_to_consultation_plan,
	sync_vaccination_to_consultation_plan,
)


class TestConsultationBillingPlan(TestCase):
	def test_lab_order_adds_one_consultation_plan_row_per_test(self):
		consultation = make_consultation()
		order = frappe._dict(
			doctype="Veterinary Lab Order",
			name="VLAB-001",
			consultation="VCON-001",
			status="Requested",
			lab_tests=[
				frappe._dict(name="ROW-1", lab_test_template="CBC", lab_test_name="Complete Blood Count", billing_item="LAB-CBC", notes="Urgent", rate=5100),
				frappe._dict(name="ROW-2", lab_test_template="UA", lab_test_name="Urinalysis", billing_item="LAB-UA"),
			],
		)

		with patch_plan_frappe(consultation, lab_rates={"CBC": 4500, "UA": 3000}):
			sync_lab_order_to_consultation_plan(order)

		self.assertEqual(len(consultation.planned_treatments), 2)
		self.assertEqual(consultation.planned_treatments[0].source_type, "Lab Order")
		self.assertEqual(consultation.planned_treatments[0].source_document, "VLAB-001")
		self.assertEqual(consultation.planned_treatments[0].source_detail_name, "ROW-1")
		self.assertEqual(consultation.planned_treatments[0].item, "LAB-CBC")
		self.assertEqual(consultation.planned_treatments[0].rate, 5100)
		self.assertEqual(consultation.planned_treatments[0].billing_status, "Pending")
		self.assertEqual(consultation.planned_treatments[0].payment_status, "Not Billed")
		consultation.save.assert_called_once_with(ignore_permissions=True)

	def test_lab_order_resave_updates_existing_editable_source_row_rate_without_duplicate(self):
		consultation = make_consultation(
			planned_treatments=[
				frappe._dict(
					source_type="Lab Order",
					source_document="VLAB-001",
					source_detail_name="ROW-1",
					item="LAB-CBC",
					rate=9999,
					qty=1,
					billing_status="Pending",
					payment_status="Not Billed",
				)
			]
		)
		order = frappe._dict(
			name="VLAB-001",
			consultation="VCON-001",
			status="Requested",
			lab_tests=[frappe._dict(name="ROW-1", lab_test_template="CBC", lab_test_name="Complete Blood Count", billing_item="LAB-CBC", rate=4500)],
		)

		with patch_plan_frappe(consultation, lab_rates={"CBC": 4500}):
			sync_lab_order_to_consultation_plan(order)

		self.assertEqual(len(consultation.planned_treatments), 1)
		self.assertEqual(consultation.planned_treatments[0].rate, 4500)
		self.assertEqual(consultation.planned_treatments[0].amount, 4500)
		consultation.save.assert_called_once_with(ignore_permissions=True)

	def test_lab_order_resave_does_not_update_submitted_source_row_rate(self):
		consultation = make_consultation(
			planned_treatments=[
				frappe._dict(
					source_type="Lab Order",
					source_document="VLAB-001",
					source_detail_name="ROW-1",
					item="LAB-CBC",
					rate=9999,
					qty=1,
					billing_status="Submitted Invoiced",
					payment_status="Unpaid",
				)
			]
		)
		order = frappe._dict(
			name="VLAB-001",
			consultation="VCON-001",
			status="Requested",
			lab_tests=[frappe._dict(name="ROW-1", lab_test_template="CBC", lab_test_name="Complete Blood Count", billing_item="LAB-CBC", rate=4500)],
		)

		with patch_plan_frappe(consultation, lab_rates={"CBC": 4500}):
			sync_lab_order_to_consultation_plan(order)

		self.assertEqual(len(consultation.planned_treatments), 1)
		self.assertEqual(consultation.planned_treatments[0].rate, 9999)
		consultation.save.assert_not_called()

	def test_vaccination_adds_consultation_plan_row(self):
		consultation = make_consultation()
		record = frappe._dict(
			doctype="Veterinary Vaccination Record",
			name="VVAC-001",
			linked_consultation="VCON-001",
			status="Draft",
			vaccine="Rabies",
			notes="First dose",
		)

		with patch_plan_frappe(consultation, vaccine={"vaccine_name": "Rabies Vaccine", "default_item": "VAC-RAB", "default_price": 7500}):
			sync_vaccination_to_consultation_plan(record)

		self.assertEqual(len(consultation.planned_treatments), 1)
		row = consultation.planned_treatments[0]
		self.assertEqual(row.source_type, "Vaccination")
		self.assertEqual(row.source_document, "VVAC-001")
		self.assertEqual(row.source_detail_name, "Rabies")
		self.assertEqual(row.item, "VAC-RAB")
		self.assertEqual(row.rate, 7500)
		self.assertEqual(row.payment_status, "Not Billed")


def make_consultation(planned_treatments=None):
	consultation = frappe._dict(name="VCON-001", planned_treatments=planned_treatments or [])
	consultation.append = lambda fieldname, row: consultation.setdefault(fieldname, []).append(frappe._dict(row)) or consultation[fieldname][-1]
	consultation.save = Mock()
	return consultation


def patch_plan_frappe(consultation, lab_rates=None, vaccine=None):
	lab_rates = lab_rates or {}
	vaccine = vaccine or {}

	def get_value(doctype, name, fields=None, as_dict=False, **kwargs):
		if doctype == "Veterinary Lab Test":
			return frappe._dict(default_rate=lab_rates.get(name))
		if doctype == "Veterinary Vaccine":
			return frappe._dict(vaccine)
		raise AssertionError(f"Unexpected get_value call: {doctype} {name} {fields}")

	frappe_stub = SimpleNamespace(
		get_doc=lambda doctype, name: consultation,
		db=SimpleNamespace(get_value=get_value),
	)
	return patch("vetedge.services.consultation_billing_plan.frappe", frappe_stub)
