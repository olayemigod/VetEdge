from __future__ import annotations

import frappe
from frappe import ValidationError
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate
from unittest.mock import patch

from vetedge.services.age import calculate_age_label


class TestVeterinaryPatient(IntegrationTestCase):
	def test_deceased_status_syncs_flag(self):
		patient = frappe.get_doc(
			{
				"doctype": "Veterinary Patient",
				"patient_name": "Test Pet",
				"primary_owner": "Test Customer",
				"species": "Dog",
				"status": "Deceased",
			}
		)

		patient.run_method("validate")

		self.assertEqual(patient.is_deceased, 1)

	def test_deceased_flag_syncs_status(self):
		patient = frappe.get_doc(
			{
				"doctype": "Veterinary Patient",
				"patient_name": "Test Pet",
				"primary_owner": "Test Customer",
				"species": "Dog",
				"is_deceased": 1,
				"status": "Active",
			}
		)

		patient.run_method("validate")

		self.assertEqual(patient.status, "Deceased")

	def test_birth_date_cannot_be_in_future(self):
		patient = frappe.get_doc(
			{
				"doctype": "Veterinary Patient",
				"patient_name": "Test Pet",
				"primary_owner": "Test Customer",
				"species": "Dog",
				"date_of_birth": add_days(nowdate(), 1),
			}
		)

		self.assertRaises(ValidationError, patient.run_method, "validate")

	def test_approximate_age_is_calculated_from_birth_date(self):
		self.assertEqual(calculate_age_label("2020-01-15", "2022-03-14"), "2 years 1 month")
		self.assertEqual(calculate_age_label("2022-03-01", "2022-03-14"), "13 days")

	def test_weight_cannot_be_negative(self):
		patient = frappe.get_doc(
			{
				"doctype": "Veterinary Patient",
				"patient_name": "Test Pet",
				"primary_owner": "Test Customer",
				"species": "Dog",
				"weight_baseline": -1,
			}
		)

		self.assertRaises(ValidationError, patient.run_method, "validate")

	def test_breed_must_belong_to_selected_species(self):
		patient = frappe.get_doc(
			{
				"doctype": "Veterinary Patient",
				"patient_name": "Test Pet",
				"primary_owner": "Test Customer",
				"species": "Dog",
				"breed": "Persian",
			}
		)

		with (
			patch("vetedge.services.patient.frappe.db.get_value", return_value="Cat"),
			patch("vetedge.services.patient.frappe.throw", side_effect=ValidationError),
		):
			self.assertRaises(ValidationError, patient.run_method, "validate")
