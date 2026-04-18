from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.medical_history import (
	get_patient_medical_history,
	get_patient_vitals_trend,
)


class TestMedicalHistory(TestCase):
	def test_medical_history_combines_consultations_and_vitals(self):
		def get_list(doctype, filters=None, fields=None, **kwargs):
			if doctype == "Veterinary Consultation":
				return [
					frappe._dict(
						name="VCON-001",
						consultation_title="Buddy - 2026-04-18 - Consultation 1",
						consultation_datetime="2026-04-18 10:00:00",
						service_branch="Main",
						consulting_practitioner_name="Dr Ada Vet",
						status="Completed",
						presenting_complaint="Vomiting",
						assessment_notes="Stable",
						treatment_plan_summary="Fluids",
					)
				]
			if doctype == "Veterinary Vital Signs":
				return [
					frappe._dict(
						name="VVS-001",
						vitals_title="Buddy - Vitals",
						consultation="VCON-001",
						recorded_on="2026-04-18 10:15:00",
						service_branch="Main",
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

		def get_all(doctype, filters=None, fields=None, **kwargs):
			if doctype == "Consultation Symptom":
				return [frappe._dict(parent="VCON-001", symptom="Vomiting", notes="Morning")]
			if doctype == "Consultation Diagnosis":
				return [frappe._dict(parent="VCON-001", diagnosis="Gastroenteritis", notes=None)]
			return []

		frappe_stub = make_frappe_stub(get_list=get_list, get_all=get_all)

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			history = get_patient_medical_history("VP-001")

		self.assertEqual([event["type"] for event in history], ["vitals", "consultation"])
		self.assertEqual(history[1]["symptoms"][0]["value"], "Vomiting")
		self.assertEqual(history[1]["diagnoses"][0]["value"], "Gastroenteritis")

	def test_vitals_trend_returns_chartable_values_only(self):
		frappe_stub = make_frappe_stub(
			get_list=lambda *args, **kwargs: [
				frappe._dict(name="VVS-001", recorded_on="2026-04-18 10:00:00", weight=12),
				frappe._dict(name="VVS-002", recorded_on="2026-04-19 10:00:00", weight=None),
			]
		)

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			trend = get_patient_vitals_trend("VP-001", "weight")

		self.assertEqual(trend, [{"name": "VVS-001", "timestamp": "2026-04-18 10:00:00", "fieldname": "weight", "value": 12.0}])

	def test_vitals_trend_rejects_non_chartable_field(self):
		frappe_stub = make_frappe_stub()

		with patch("vetedge.services.medical_history.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, get_patient_vitals_trend, "VP-001", "notes")


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args, **kwargs: True),
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
