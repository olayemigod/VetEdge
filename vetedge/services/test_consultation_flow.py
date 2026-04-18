from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.consultation_flow import (
	get_next_daily_consultation_number,
	validate_consultation,
	validate_consultation_children,
	validate_completion_requirements,
	validate_service_branch_access,
)


class TestConsultationFlow(TestCase):
	def test_consultation_resolves_owner_and_allows_cross_branch_service(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return None
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			validate_consultation(doc)

		self.assertEqual(doc.primary_owner, "CUST-001")
		self.assertEqual(doc.service_branch, "Branch B")
		self.assertEqual(doc.daily_consultation_number, 1)
		self.assertEqual(doc.consultation_title, "Buddy - 2026-04-18 - Consultation 1 - Branch B")

	def test_consultation_title_uses_doctor_full_name(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner="doctor@example.com",
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch="Branch B",
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return "Dr Ada Vet"
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			validate_consultation(doc)

		self.assertEqual(doc.consulting_practitioner_name, "Dr Ada Vet")
		self.assertEqual(
			doc.consultation_title,
			"Buddy - 2026-04-18 - Consultation 1 - Dr Ada Vet - Branch B",
		)

	def test_daily_consultation_number_increments_per_patient_day(self):
		frappe_stub = make_frappe_stub(
			get_all=lambda *args, **kwargs: [
				frappe._dict(daily_consultation_number=1),
				frappe._dict(daily_consultation_number=2),
			]
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			number = get_next_daily_consultation_number("VP-001", "2026-04-18 15:30:00")

		self.assertEqual(number, 3)

	def test_consultation_defaults_service_branch_from_patient_home_branch(self):
		doc = frappe._dict(
			patient="VP-001",
			primary_owner=None,
			consulting_practitioner=None,
			consulting_practitioner_name=None,
			daily_consultation_number=None,
			service_branch=None,
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "User" and fields == "full_name":
				return None
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(primary_owner="CUST-001", default_branch="Branch A")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value,
				exists=lambda *args, **kwargs: False,
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			validate_consultation(doc)

		self.assertEqual(doc.service_branch, "Branch A")

	def test_consultation_requires_service_branch_when_patient_has_no_default(self):
		doc = frappe._dict(
			patient="VP-001",
			consulting_practitioner=None,
			service_branch=None,
			consultation_datetime="2026-04-18 10:00:00",
			status="Draft",
			company="Test Company",
			symptoms=[],
			diagnoses=[],
			planned_treatments=[],
		)

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					primary_owner="CUST-001",
					default_branch=None,
				),
				exists=lambda *args, **kwargs: False,
			)
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_consultation, doc)

	def test_child_rows_validate_links_and_qty(self):
		doc = frappe._dict(
			symptoms=[frappe._dict(symptom="Vomiting")],
			diagnoses=[frappe._dict(diagnosis="Gastroenteritis")],
			planned_treatments=[
				frappe._dict(
					item="CONSULT-ITEM",
					qty=1,
					service_type="Consultation",
					treatment_type="Medication",
				)
			],
		)

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda doctype, name, fields=None, **kwargs: frappe._dict(disabled=0)
				if doctype == "Item"
				else 0,
			),
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname == "disabled"),
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			validate_consultation_children(doc)

	def test_completion_requires_vitals_when_setting_is_active(self):
		doc = frappe._dict(name="VCON-001", status="Completed")

		with (
			patch("vetedge.services.consultation_flow.is_vitals_required_before_completion", return_value=True),
			patch("vetedge.services.consultation_flow.has_vitals_for_consultation", return_value=False),
			patch("vetedge.services.consultation_flow.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_completion_requirements, doc)

	def test_branch_assignment_is_enforced_when_assignment_doctype_exists(self):
		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(exists=lambda *args, **kwargs: args == ("DocType", "Branch User Assignment")),
			get_all=lambda *args, **kwargs: [],
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: False),
		)

		with patch("vetedge.services.consultation_flow.frappe", frappe_stub):
			self.assertRaises(
				frappe.PermissionError,
				validate_service_branch_access,
				frappe._dict(service_branch="Main", consulting_practitioner=None),
			)


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args, **kwargs: False),
		get_all=lambda *args, **kwargs: [],
		get_meta=lambda doctype: SimpleNamespace(
			has_field=lambda fieldname: False,
			get_title_field=lambda: "patient_name" if doctype == "Veterinary Patient" else "name",
		),
		session=SimpleNamespace(user="test@example.com"),
		throw=throw,
		utils=SimpleNamespace(now_datetime=lambda: "2026-04-18 10:00:00"),
		ValidationError=frappe.ValidationError,
		PermissionError=frappe.PermissionError,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub
