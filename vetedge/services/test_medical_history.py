from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.medical_history import (
	get_patient_medical_history_view,
	get_patient_medical_history,
	get_patient_vitals_trend,
)


class TestMedicalHistory(TestCase):
	def test_medical_history_combines_consultations_and_vitals(self):
		frappe_stub = make_frappe_stub(get_list=get_list_for_history, get_all=get_all_for_history)

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			history = get_patient_medical_history("VP-001", from_date="2026-04-01", to_date="2026-04-30")

		self.assertEqual([event["type"] for event in history], ["vitals", "consultation"])
		self.assertEqual(history[1]["symptoms"][0]["value"], "Vomiting")
		self.assertEqual(history[1]["diagnoses"][0]["value"], "Gastroenteritis")

	def test_medical_history_view_returns_patient_sections_and_cross_branch_records(self):
		frappe_stub = make_frappe_stub(get_list=get_list_for_history, get_all=get_all_for_history)

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			view = get_patient_medical_history_view("VP-001", "2026-04-01", "2026-04-30")

		self.assertEqual(view["summary"]["patient_name"], "Buddy")
		self.assertEqual(view["summary"]["latest_weight"], 12)
		self.assertEqual(view["consultations"][0]["service_branch"], "Branch B")
		self.assertEqual(view["vitals"][0]["service_branch"], "Branch C")
		self.assertEqual(view["diagnoses"][0]["diagnosis"], "Gastroenteritis")
		self.assertEqual(view["symptoms"][0]["symptom"], "Vomiting")
		self.assertEqual(view["treatments"][0]["item"], "Fluid Therapy")
		self.assertIn("temperature", view["trends"])
		self.assertIn("vaccination_history", view["placeholders"])

	def test_medical_history_view_handles_empty_history(self):
		frappe_stub = make_frappe_stub(get_list=lambda *args, **kwargs: [], get_all=lambda *args, **kwargs: [])

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			view = get_patient_medical_history_view("VP-001", "2026-04-01", "2026-04-30")

		self.assertEqual(view["consultations"], [])
		self.assertEqual(view["vitals"], [])
		self.assertEqual(view["diagnoses"], [])
		self.assertEqual(view["symptoms"], [])
		self.assertEqual(view["treatments"], [])

	def test_history_date_range_is_applied_to_consultations_and_vitals(self):
		calls = []

		def get_list(doctype, filters=None, fields=None, **kwargs):
			calls.append((doctype, filters))
			return []

		frappe_stub = make_frappe_stub(get_list=get_list)

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			get_patient_medical_history_view("VP-001", "2026-04-01", "2026-04-30")

		consultation_filters = [filters for doctype, filters in calls if doctype == "Veterinary Consultation"]
		vitals_filters = [filters for doctype, filters in calls if doctype == "Veterinary Vital Signs"]
		self.assertTrue(any("consultation_datetime" in filters for filters in consultation_filters))
		self.assertTrue(any("recorded_on" in filters for filters in vitals_filters))

	def test_vitals_trend_returns_chartable_values_only(self):
		frappe_stub = make_frappe_stub(
			get_list=lambda *args, **kwargs: [
				frappe._dict(name="VVS-001", recorded_on="2026-04-18 10:00:00", weight=12),
				frappe._dict(name="VVS-002", recorded_on="2026-04-19 10:00:00", weight=None),
			]
		)

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			trend = get_patient_vitals_trend("VP-001", "weight", from_date="2026-04-01", to_date="2026-04-30")

		self.assertEqual(trend, [{"name": "VVS-001", "timestamp": "2026-04-18 10:00:00", "fieldname": "weight", "value": 12.0}])

	def test_vitals_trend_rejects_non_chartable_field(self):
		frappe_stub = make_frappe_stub()

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			self.assertRaises(
				frappe.ValidationError,
				get_patient_vitals_trend,
				"VP-001",
				"notes",
				from_date="2026-04-01",
				to_date="2026-04-30",
			)


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(
			exists=lambda *args, **kwargs: True,
			get_value=lambda *args, **kwargs: frappe._dict(
				patient_name="Buddy",
				species="Dog",
				breed="Labrador",
				primary_owner="CUST-001",
				default_branch="Branch A",
			),
		),
		get_all=lambda *args, **kwargs: [],
		get_list=lambda *args, **kwargs: [],
		has_permission=lambda *args, **kwargs: True,
		throw=throw,
		ValidationError=frappe.ValidationError,
		PermissionError=frappe.PermissionError,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub


def get_list_for_history(doctype, filters=None, fields=None, **kwargs):
	if doctype == "Veterinary Consultation":
		if fields == ["name", "consultation_datetime"]:
			return [frappe._dict(name="VCON-001", consultation_datetime="2026-04-18 10:00:00")]
		if fields == ["name", "consultation_datetime", "service_branch", "consulting_practitioner_name"]:
			return [
				frappe._dict(
					name="VCON-001",
					consultation_datetime="2026-04-18 10:00:00",
					service_branch="Branch B",
					consulting_practitioner_name="Dr Ada Vet",
				)
			]
		return [
			frappe._dict(
				name="VCON-001",
				consultation_title="Buddy - 2026-04-18 - Consultation 1",
				consultation_datetime="2026-04-18 10:00:00",
				service_branch="Branch B",
				consulting_practitioner_name="Dr Ada Vet",
				status="Completed",
				presenting_complaint="Vomiting",
				assessment_notes="Stable",
				treatment_plan_summary="Fluids",
			)
		]
	if doctype == "Veterinary Vital Signs":
		if fields == ["name", "recorded_on", "weight", "temperature"]:
			return [frappe._dict(name="VVS-001", recorded_on="2026-04-18 10:15:00", weight=12, temperature=38.5)]
		if len(fields or []) == 3:
			fieldname = fields[2]
			return [frappe._dict(name="VVS-001", recorded_on="2026-04-18 10:15:00", **{fieldname: 12})]
		return [
			frappe._dict(
				name="VVS-001",
				vitals_title="Buddy - Vitals",
				consultation="VCON-001",
				recorded_on="2026-04-18 10:15:00",
				service_branch="Branch C",
				recorded_by="doctor@example.com",
				temperature=38.5,
				weight=12,
				heart_rate=90,
				respiratory_rate=20,
				body_condition_score="5",
				hydration_status="Normal",
				mucous_membrane="Pink",
				capillary_refill_time="2 sec",
				pain_score="1",
				appetite_status="Reduced",
				notes="Alert",
			)
		]
	return []


def get_all_for_history(doctype, filters=None, fields=None, **kwargs):
	if doctype == "Consultation Symptom":
		return [frappe._dict(parent="VCON-001", symptom="Vomiting", notes="Morning")]
	if doctype == "Consultation Diagnosis":
		return [
			frappe._dict(
				parent="VCON-001",
				diagnosis="Gastroenteritis",
				diagnosis_type="Primary",
				notes=None,
			)
		]
	if doctype == "Planned Treatment Item":
		return [
			frappe._dict(
				parent="VCON-001",
				item="Fluid Therapy",
				qty=1,
				uom="Nos",
				service_type="Treatment",
				treatment_type="Medication",
				notes="SQ fluids",
			)
		]
	return []
