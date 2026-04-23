from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.treatment_items import (
	apply_planned_treatment_defaults,
	get_treatment_item_defaults,
	validate_treatment_item_profile,
)


class TestTreatmentItems(TestCase):
	def test_get_treatment_item_defaults_returns_profile(self):
		frappe_stub = make_frappe_stub(
			exists=lambda doctype, name=None: doctype == "DocType",
			get_value=lambda doctype, name, fields=None, as_dict=False: frappe._dict(
				item="MED-001",
				service_type="Medication Service",
				treatment_type="Medication",
				shelf_life_in_days=365,
			),
		)

		with patch("vetedge.services.treatment_items.frappe", frappe_stub):
			defaults = get_treatment_item_defaults("MED-001")

		self.assertEqual(defaults.service_type, "Medication Service")
		self.assertEqual(defaults.treatment_type, "Medication")
		self.assertEqual(defaults.shelf_life_in_days, 365)

	def test_apply_planned_treatment_defaults_populates_missing_fields(self):
		row = frappe._dict(item="MED-001", service_type=None, treatment_type=None)

		with patch(
			"vetedge.services.treatment_items.get_treatment_item_defaults",
			return_value=SimpleNamespace(service_type="Medication Service", treatment_type="Medication", shelf_life_in_days=180),
		):
			apply_planned_treatment_defaults(row)

		self.assertEqual(row.service_type, "Medication Service")
		self.assertEqual(row.treatment_type, "Medication")

	def test_validate_treatment_item_profile_accepts_valid_links(self):
		doc = frappe._dict(
			item="MED-001",
			service_type="Medication Service",
			treatment_type="Medication",
			shelf_life_in_days=180,
		)
		set_calls = []
		frappe_stub = make_frappe_stub(
			get_value=lambda doctype, name, fields=None, as_dict=False: frappe._dict(
				disabled=0,
			)
			if doctype == "Item"
			else 0,
			set_value=lambda *args, **kwargs: set_calls.append(args),
		)

		with patch("vetedge.services.treatment_items.frappe", frappe_stub):
			validate_treatment_item_profile(doc)

		self.assertEqual(set_calls[0][0], "Item")
		self.assertEqual(set_calls[0][1], "MED-001")
		self.assertEqual(set_calls[0][2], "shelf_life_in_days")
		self.assertEqual(set_calls[0][3], 180)

	def test_validate_treatment_item_profile_rejects_negative_shelf_life(self):
		doc = frappe._dict(
			item="MED-001",
			service_type="Medication Service",
			treatment_type="Medication",
			shelf_life_in_days=-1,
		)
		frappe_stub = make_frappe_stub(
			get_value=lambda doctype, name, fields=None, as_dict=False: frappe._dict(disabled=0)
			if doctype == "Item"
			else 0,
		)

		with (
			patch("vetedge.services.treatment_items.frappe", frappe_stub),
			patch("vetedge.services.treatment_items.frappe.throw", side_effect=frappe.ValidationError),
		):
			self.assertRaises(frappe.ValidationError, validate_treatment_item_profile, doc)


def make_frappe_stub(exists=None, get_value=None, set_value=None):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	return SimpleNamespace(
		db=SimpleNamespace(
			exists=exists or (lambda *args, **kwargs: True),
			get_value=get_value or (lambda *args, **kwargs: None),
			set_value=set_value or (lambda *args, **kwargs: None),
		),
		get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname in {"disabled", "shelf_life_in_days"}),
		throw=throw,
		ValidationError=frappe.ValidationError,
	)
