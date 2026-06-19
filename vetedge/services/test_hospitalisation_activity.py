from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services import hospitalisation


def hospitalisation_doc(**values):
	defaults = {
		"doctype": "Veterinary Hospitalisation",
		"name": "VHOS-001",
		"status": "Under Care",
		"payment_gate_status": "Allowed",
		"payment_gate_message": "Payment gate passed.",
		"activities": [],
	}
	defaults.update(values)
	doc = frappe._dict(defaults)
	doc.is_new = lambda: False
	return doc


def activity(**values):
	defaults = {
		"activity_type": "Nursing Note",
		"clinical_notes": "Resting comfortably",
		"billable": 0,
		"stock_affecting": 0,
		"billing_status": None,
		"stock_status": None,
	}
	defaults.update(values)
	return frappe._dict(defaults)


class TestHospitalisationActivities(TestCase):
	def test_hospitalisation_can_be_saved_with_no_activities(self):
		doc = hospitalisation_doc(activities=[])

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		self.assertEqual(doc.activities, [])
		self.assertEqual(doc.status, "Under Care")

	def test_clinical_only_nursing_note_activity_defaults_to_non_billable_non_stock(self):
		doc = hospitalisation_doc(activities=[activity(activity_type="Nursing Note")])

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		row = doc.activities[0]
		self.assertEqual(row.activity_type, "Nursing Note")
		self.assertEqual(row.billing_status, "Not Billable")
		self.assertEqual(row.stock_status, "Not Applicable")
		self.assertFalse(row.get("item"))

	def test_medication_activity_marked_billable_defaults_to_pending_charge(self):
		doc = hospitalisation_doc(activities=[activity(activity_type="Medication", billable=1)])

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		self.assertEqual(doc.activities[0].billing_status, "Pending Charge")

	def test_billing_status_defaults_for_billable_and_non_billable_activities(self):
		doc = hospitalisation_doc(
			activities=[
				activity(activity_type="Feeding", billable=0, billing_status="Pending Charge"),
				activity(activity_type="Procedure", billable=1, billing_status="Not Billable"),
			]
		)

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		self.assertEqual(doc.activities[0].billing_status, "Not Billable")
		self.assertEqual(doc.activities[1].billing_status, "Pending Charge")

	def test_stock_status_defaults_for_stock_and_non_stock_activities(self):
		doc = hospitalisation_doc(
			activities=[
				activity(activity_type="Medication", stock_affecting=1, stock_status="Not Applicable"),
				activity(activity_type="Owner Communication", stock_affecting=0, stock_status="Pending"),
			]
		)

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		self.assertEqual(doc.activities[0].stock_status, "Pending")
		self.assertEqual(doc.activities[1].stock_status, "Not Applicable")

	def test_vaccination_activity_can_be_recorded(self):
		doc = hospitalisation_doc(activities=[activity(activity_type="Vaccination", clinical_notes="Rabies vaccine recorded")])

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		self.assertEqual(doc.activities[0].activity_type, "Vaccination")
		self.assertEqual(doc.activities[0].billing_status, "Not Billable")

	def test_vaccination_activity_does_not_change_hospitalisation_status(self):
		doc = hospitalisation_doc(status="Admitted", activities=[activity(activity_type="Vaccination")])

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		self.assertEqual(doc.status, "Admitted")

	def test_activity_does_not_bypass_payment_gate_or_change_payment_gate_status(self):
		doc = hospitalisation_doc(
			status="Draft",
			payment_gate_status="Blocked",
			payment_gate_message="A submitted Sales Invoice is required before hospitalisation care can proceed.",
			activities=[activity(activity_type="Medication", billable=1, stock_affecting=1)],
		)

		with activity_context():
			hospitalisation.validate_hospitalisation(doc)

		self.assertEqual(doc.status, "Draft")
		self.assertEqual(doc.payment_gate_status, "Blocked")
		self.assertEqual(
			doc.payment_gate_message,
			"A submitted Sales Invoice is required before hospitalisation care can proceed.",
		)


def activity_context():
	return patch.object(hospitalisation, "frappe", SimpleNamespace(session=SimpleNamespace(user="vet@example.com")))
