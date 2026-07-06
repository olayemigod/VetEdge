from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.vitals import (
	create_vitals_from_consultation,
	get_latest_vitals_for_consultation,
	validate_vital_signs,
)


class TestVitals(TestCase):
	def test_vitals_feature_flag_blocks_validation(self):
		doc = frappe._dict(patient="VP-001", service_branch="Branch A")

		with (
			patch("vetedge.services.vitals.frappe", make_frappe_stub()),
			patch("vetedge.services.vitals.is_enabled", return_value=False),
		):
			self.assertRaises(frappe.ValidationError, validate_vital_signs, doc)

	def test_vitals_resolve_patient_and_branch_from_consultation(self):
		doc = frappe._dict(
			consultation="VCON-001",
			patient=None,
			service_branch=None,
			recorded_by=None,
			recorded_on=None,
			temperature=38.5,
			weight=12,
			heart_rate=90,
			respiratory_rate=20,
		)

		def get_value(doctype, name, fields=None, **kwargs):
			if fields == "patient_name":
				return "Buddy"
			return frappe._dict(patient="VP-001", service_branch="Branch B")

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=get_value
			)
		)

		with patch("vetedge.services.vitals.frappe", frappe_stub):
			validate_vital_signs(doc)

		self.assertEqual(doc.patient, "VP-001")
		self.assertEqual(doc.service_branch, "Branch B")
		self.assertEqual(doc.recorded_by, "test@example.com")
		self.assertEqual(doc.vitals_title, "Buddy - Vitals - 2026-04-18 10:00 - Branch B")

	def test_create_vitals_from_consultation_inserts_real_vitals_doc(self):
		created = []

		def get_doc(data):
			doc = frappe._dict(data)
			doc.name = "VVS-001"
			doc.insert = lambda: created.append(doc)
			return doc

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					patient="VP-001",
					service_branch="Branch B",
				)
			),
			get_doc=get_doc,
			parse_json=lambda value: value,
		)

		with (
			patch("vetedge.services.vitals.frappe", frappe_stub),
			patch("vetedge.services.vitals.can_access_consultation"),
			patch("vetedge.services.vitals.can_access_branch_data"),
		):
			name = create_vitals_from_consultation(
				"VCON-001",
				{
					"recorded_on": "2026-04-19 09:30:00",
					"temperature": 38.5,
					"weight": 12,
				},
			)

		self.assertEqual(name, "VVS-001")
		self.assertEqual(created[0].doctype, "Veterinary Vital Signs")
		self.assertEqual(created[0].consultation, "VCON-001")
		self.assertEqual(created[0].patient, "VP-001")
		self.assertEqual(created[0].service_branch, "Branch B")

	def test_vitals_patient_must_match_consultation(self):
		doc = frappe._dict(
			consultation="VCON-001",
			patient="VP-OTHER",
			service_branch=None,
			recorded_by=None,
			recorded_on=None,
		)

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				get_value=lambda *args, **kwargs: frappe._dict(
					patient="VP-001",
					service_branch="Branch B",
				)
			)
		)

		with patch("vetedge.services.vitals.frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, validate_vital_signs, doc)

	def test_negative_vitals_are_rejected(self):
		doc = frappe._dict(
			consultation=None,
			patient="VP-001",
			service_branch="Branch A",
			recorded_by="test@example.com",
			recorded_on="2026-04-18 10:00:00",
			weight=-1,
		)

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(get_value=lambda *args, **kwargs: "Buddy"),
		)

		with (
			patch("vetedge.services.vitals.frappe", frappe_stub),
			patch.object(frappe_stub, "throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_vital_signs, doc)

	def test_latest_vitals_uses_current_consultation_only(self):
		rows_by_filters = {
			(("consultation", "VCON-001"),): [],
			(("patient", "VP-001"),): [frappe._dict(name="VVS-001", patient="VP-001")],
		}
		queried_filters = []

		def get_list(doctype, filters=None, **kwargs):
			queried_filters.append(filters)
			return rows_by_filters.get(tuple(sorted((filters or {}).items())), [])

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(get_value=lambda *args, **kwargs: "VP-001"),
			get_list=get_list,
		)

		with (
			patch("vetedge.services.vitals.frappe", frappe_stub),
			patch("vetedge.services.vitals.can_access_consultation"),
		):
			vitals = get_latest_vitals_for_consultation("VCON-001")

		self.assertIsNone(vitals)
		self.assertEqual(queried_filters, [{"consultation": "VCON-001"}])

	def test_create_vitals_blocks_when_feature_disabled(self):
		with (
			patch("vetedge.services.vitals.frappe", make_frappe_stub()),
			patch("vetedge.services.vitals.is_enabled", return_value=False),
		):
			self.assertRaises(frappe.ValidationError, create_vitals_from_consultation, "VCON-001", {})


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(get_value=lambda *args, **kwargs: None, exists=lambda *args, **kwargs: True),
		get_list=lambda *args, **kwargs: [],
		get_meta=lambda doctype: SimpleNamespace(
			get_title_field=lambda: "patient_name" if doctype == "Veterinary Patient" else "name"
		),
		get_doc=lambda *args, **kwargs: None,
		get_roles=lambda *args, **kwargs: ["VetEdge Doctor"],
		has_permission=lambda *args, **kwargs: True,
		parse_json=lambda value: value,
		session=SimpleNamespace(user="test@example.com"),
		throw=throw,
		utils=SimpleNamespace(now_datetime=lambda: "2026-04-18 10:00:00"),
		ValidationError=frappe.ValidationError,
		PermissionError=frappe.PermissionError,
	)
	for key, value in overrides.items():
		if key == "db" and not hasattr(value, "exists"):
			value.exists = lambda *args, **kwargs: True
		setattr(stub, key, value)
	return stub
