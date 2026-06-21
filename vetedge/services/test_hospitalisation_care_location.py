from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation


def row(**values):
	doc = frappe._dict(values)
	doc.get = doc.get
	doc.set = lambda key, value: setattr(doc, key, value)
	doc.save = Mock()
	doc.insert = Mock()
	doc.is_new = lambda: not bool(doc.get("name"))
	return doc


class CareLocationFrappeStub:
	def __init__(self):
		self.hospitalisations = {}
		self.locations = {}
		self.logs = []
		self.created_logs = []
		self.session = SimpleNamespace(user="vet@example.com")
		self.ValidationError = frappe.ValidationError
		self.throw = Mock(side_effect=frappe.ValidationError)
		self.db = SimpleNamespace(exists=self.exists, get_value=self.get_value)

	def exists(self, doctype, name=None):
		if doctype == hospitalisation.HOSPITALISATION_DOCTYPE:
			return name in self.hospitalisations
		if doctype == hospitalisation.CARE_LOCATION_DOCTYPE:
			return name in self.locations
		return True

	def get_value(self, doctype, name, fieldname=None):
		if doctype == hospitalisation.HOSPITALISATION_DOCTYPE:
			return self.hospitalisations[name].get(fieldname)
		return None

	def get_doc(self, doctype, name=None):
		if isinstance(doctype, dict):
			new_log = row(**doctype, name=f"VLOC-LOG-{len(self.created_logs) + 1}")
			new_log.insert = Mock(side_effect=lambda **kwargs: self.created_logs.append(new_log))
			return new_log
		if doctype == hospitalisation.HOSPITALISATION_DOCTYPE:
			return self.hospitalisations[name]
		if doctype == hospitalisation.CARE_LOCATION_DOCTYPE:
			return self.locations[name]
		if doctype == hospitalisation.CARE_LOCATION_LOG_DOCTYPE:
			for log in self.logs + self.created_logs:
				if log.name == name:
					return log
		raise KeyError((doctype, name))

	def get_all(self, doctype, filters=None, fields=None, **kwargs):
		filters = filters or {}
		if doctype == hospitalisation.CARE_LOCATION_LOG_DOCTYPE:
			results = []
			for log in self.logs + self.created_logs:
				if all(log.get(key) == value for key, value in filters.items()):
					results.append(frappe._dict({field: log.get(field) for field in fields or ["name"]}))
			return results[: kwargs.get("limit") or len(results)]
		if doctype == hospitalisation.CARE_LOCATION_DOCTYPE:
			results = []
			for loc in self.locations.values():
				matched = True
				for key, value in filters.items():
					if loc.get(key) != value:
						matched = False
						break
				if matched:
					results.append(frappe._dict({field: loc.get(field) for field in fields or ["name"]}))
			return results
		return []


def make_hospitalisation(name="VHOS-001", status="Admitted", branch="Main", care_location=None):
	return row(
		doctype=hospitalisation.HOSPITALISATION_DOCTYPE,
		name=name,
		status=status,
		service_branch=branch,
		patient="VP-001",
		customer="CUST-001",
		care_location=care_location,
		care_location_assigned_on=None,
		care_location_released_on=None,
		care_location_status=None,
		payment_gate_status="Not Checked",
		sales_invoice=None,
		charge_items=[],
		activities=[],
	)


def make_location(name="ICU Cage 1", branch="Main", capacity=1, status="Available", enabled=1, location_type="ICU"):
	return row(
		doctype=hospitalisation.CARE_LOCATION_DOCTYPE,
		name=name,
		location_name=name,
		branch=branch,
		capacity=capacity,
		status=status,
		enabled=enabled,
		location_type=location_type,
	)


class TestHospitalisationCareLocation(TestCase):
	def test_care_location_doctype_metadata_exists(self):
		path = Path(__file__).resolve().parents[1] / "veterinary" / "doctype" / "veterinary_care_location" / "veterinary_care_location.json"
		data = json.loads(path.read_text())
		self.assertEqual(data["name"], "Veterinary Care Location")
		self.assertTrue(any(field.get("fieldname") == "enabled" for field in data["fields"]))

	def test_assign_care_location_updates_hospitalisation_and_log(self):
		stub = CareLocationFrappeStub()
		stub.hospitalisations["VHOS-001"] = make_hospitalisation()
		stub.locations["ICU Cage 1"] = make_location()
		with patch.object(hospitalisation, "frappe", stub), patch.object(hospitalisation, "require_internal_user"):
			result = hospitalisation.assign_hospitalisation_care_location("VHOS-001", "ICU Cage 1", notes="Moved in")
		doc = stub.hospitalisations["VHOS-001"]
		self.assertTrue(result["assigned"])
		self.assertEqual(doc.care_location, "ICU Cage 1")
		self.assertEqual(doc.care_location_status, "Assigned")
		doc.save.assert_called()
		self.assertEqual(len(stub.created_logs), 1)

	def test_single_capacity_location_blocks_second_active_hospitalisation(self):
		stub = CareLocationFrappeStub()
		stub.hospitalisations["VHOS-001"] = make_hospitalisation("VHOS-001")
		stub.hospitalisations["VHOS-002"] = make_hospitalisation("VHOS-002")
		stub.locations["ICU Cage 1"] = make_location(capacity=1)
		stub.logs.append(row(name="LOG-1", hospitalisation="VHOS-001", care_location="ICU Cage 1", status="Active"))
		with patch.object(hospitalisation, "frappe", stub), patch.object(hospitalisation, "require_internal_user"):
			self.assertRaises(frappe.ValidationError, hospitalisation.assign_hospitalisation_care_location, "VHOS-002", "ICU Cage 1")

	def test_multi_capacity_allows_until_full(self):
		stub = CareLocationFrappeStub()
		for name in ["VHOS-001", "VHOS-002", "VHOS-003", "VHOS-004"]:
			stub.hospitalisations[name] = make_hospitalisation(name)
		stub.locations["Ward A"] = make_location("Ward A", capacity=3, location_type="Ward")
		stub.logs.extend([
			row(name="LOG-1", hospitalisation="VHOS-001", care_location="Ward A", status="Active"),
			row(name="LOG-2", hospitalisation="VHOS-002", care_location="Ward A", status="Active"),
		])
		with patch.object(hospitalisation, "frappe", stub), patch.object(hospitalisation, "require_internal_user"):
			result = hospitalisation.assign_hospitalisation_care_location("VHOS-003", "Ward A")
			self.assertTrue(result["assigned"])
			self.assertRaises(frappe.ValidationError, hospitalisation.assign_hospitalisation_care_location, "VHOS-004", "Ward A")

	def test_release_frees_location_and_allows_reassignment(self):
		stub = CareLocationFrappeStub()
		stub.hospitalisations["VHOS-001"] = make_hospitalisation(care_location="ICU Cage 1")
		stub.hospitalisations["VHOS-002"] = make_hospitalisation("VHOS-002")
		stub.locations["ICU Cage 1"] = make_location(status="Occupied")
		stub.logs.append(row(name="LOG-1", hospitalisation="VHOS-001", care_location="ICU Cage 1", status="Active"))
		with patch.object(hospitalisation, "frappe", stub), patch.object(hospitalisation, "require_internal_user"):
			release = hospitalisation.release_hospitalisation_care_location("VHOS-001")
			assign = hospitalisation.assign_hospitalisation_care_location("VHOS-002", "ICU Cage 1")
		self.assertTrue(release["released"])
		self.assertTrue(assign["assigned"])
		self.assertIsNone(stub.hospitalisations["VHOS-001"].care_location)
		self.assertEqual(stub.logs[0].status, "Released")

	def test_branch_mismatch_blocks_assignment(self):
		stub = CareLocationFrappeStub()
		stub.hospitalisations["VHOS-001"] = make_hospitalisation(branch="Main")
		stub.locations["Cage B"] = make_location("Cage B", branch="Other")
		with patch.object(hospitalisation, "frappe", stub), patch.object(hospitalisation, "require_internal_user"):
			self.assertRaises(frappe.ValidationError, hospitalisation.assign_hospitalisation_care_location, "VHOS-001", "Cage B")

	def test_assign_release_do_not_touch_billing_stock_or_clinical_status(self):
		stub = CareLocationFrappeStub()
		doc = make_hospitalisation(status="Under Care")
		doc.payment_gate_status = "Blocked"
		doc.charge_items = [row(name="CHG-1")]
		doc.activities = [row(name="ACT-1")]
		stub.hospitalisations["VHOS-001"] = doc
		stub.locations["Ward A"] = make_location("Ward A", capacity=2)
		with patch.object(hospitalisation, "frappe", stub), patch.object(hospitalisation, "require_internal_user"):
			hospitalisation.assign_hospitalisation_care_location("VHOS-001", "Ward A")
			hospitalisation.release_hospitalisation_care_location("VHOS-001")
		self.assertEqual(doc.status, "Under Care")
		self.assertEqual(doc.payment_gate_status, "Blocked")
		self.assertEqual(len(doc.charge_items), 1)
		self.assertEqual(len(doc.activities), 1)
		self.assertIsNone(doc.sales_invoice)

	def test_available_location_api_returns_slots(self):
		stub = CareLocationFrappeStub()
		stub.hospitalisations["VHOS-001"] = make_hospitalisation("VHOS-001")
		stub.locations["Ward A"] = make_location("Ward A", capacity=3, location_type="Ward")
		stub.logs.append(row(name="LOG-1", hospitalisation="VHOS-001", care_location="Ward A", status="Active"))
		with patch.object(hospitalisation, "frappe", stub), patch.object(hospitalisation, "require_internal_user"):
			locations = hospitalisation.get_available_care_locations(branch="Main", location_type="Ward")
		self.assertEqual(len(locations), 1)
		self.assertEqual(locations[0]["available_slots"], 2)

	def test_discharge_readiness_warns_when_care_location_assigned(self):
		doc = make_hospitalisation(care_location="Ward A")
		doc.discharge_summary = "Ready"
		with (
			patch.object(hospitalisation, "get_pending_billable_activities_without_charges", return_value=[]),
			patch.object(hospitalisation, "get_pending_hospitalisation_charge_items", return_value=[]),
			patch.object(hospitalisation, "get_pending_stock_activities", return_value=[]),
			patch.object(hospitalisation, "get_hospitalisation_discharge_billing_state", return_value=({}, {"can_proceed": True, "message": ""})),
		):
			readiness = hospitalisation.build_hospitalisation_discharge_readiness(doc)
		self.assertIn("Release Care Location", readiness["recommended_actions"])
		self.assertTrue(readiness["can_discharge"])
