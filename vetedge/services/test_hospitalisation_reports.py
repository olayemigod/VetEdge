from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation_reports as reports


def row(**values):
	doc = frappe._dict(values)
	doc.get = doc.get
	doc.set = lambda key, value: setattr(doc, key, value)
	doc.save = Mock()
	return doc


def make_hospitalisation(
	name,
	status="Admitted",
	admission_datetime="2026-06-18 09:00:00",
	care_location=None,
	charge_items=None,
	activities=None,
):
	return row(
		doctype=reports.HOSPITALISATION_DOCTYPE,
		name=name,
		patient=f"VP-{name[-1]}",
		customer=f"CUST-{name[-1]}",
		service_branch="Main",
		admission_datetime=admission_datetime,
		discharge_datetime="2026-06-20 10:00:00" if status == "Discharged" else None,
		status=status,
		care_level="ICU",
		care_location=care_location,
		attending_veterinarian="vet@example.com",
		invoice_status="Draft",
		payment_gate_status="Blocked",
		sales_invoice=None,
		follow_up_date=None,
		discharge_summary="Ready" if status == "Ready for Discharge" else None,
		modified="2026-06-21 10:00:00",
		charge_items=charge_items or [],
		activities=activities or [],
	)


class ReportFrappeStub:
	def __init__(self):
		self.hospitalisations = {}
		self.locations = {}
		self.logs = []
		self.db = SimpleNamespace(exists=self.exists, get_value=self.get_value, set_value=Mock())
		self._dict = frappe._dict
		self.parse_json = frappe.parse_json

	def exists(self, doctype, name=None):
		if doctype == reports.HOSPITALISATION_DOCTYPE:
			return name in self.hospitalisations
		if doctype == "Sales Invoice":
			return False
		return True

	def get_value(self, doctype, name, fieldname=None, **kwargs):
		if doctype == reports.HOSPITALISATION_DOCTYPE:
			return self.hospitalisations[name].get(fieldname)
		return None

	def get_doc(self, doctype, name=None):
		if doctype == reports.HOSPITALISATION_DOCTYPE:
			return self.hospitalisations[name]
		raise KeyError((doctype, name))

	def get_all(self, doctype, filters=None, fields=None, **kwargs):
		filters = filters or {}
		if doctype == reports.HOSPITALISATION_DOCTYPE:
			return [frappe._dict(name=doc.name) for doc in self.hospitalisations.values() if self.matches(doc, filters)]
		if doctype == reports.CARE_LOCATION_DOCTYPE:
			return [self.project(loc, fields) for loc in self.locations.values() if self.matches(loc, filters)]
		if doctype == reports.CARE_LOCATION_LOG_DOCTYPE:
			return [self.project(log, fields) for log in self.logs if self.matches(log, filters)]
		return []

	def matches(self, doc, filters):
		for key, value in filters.items():
			actual = doc.get(key)
			if isinstance(value, (list, tuple)) and len(value) == 2 and value[0] == "in":
				if actual not in value[1]:
					return False
			elif actual != value:
				return False
		return True

	def project(self, doc, fields):
		return frappe._dict({field: doc.get(field) for field in fields or ["name"]})


def make_stub():
	stub = ReportFrappeStub()
	stub.hospitalisations["VHOS-001"] = make_hospitalisation(
		"VHOS-001",
		status="Admitted",
		care_location="Ward A",
		charge_items=[
			row(source_activity="daily-1", charge_category="Daily Stay", billing_status="Pending Invoice", item="HOSP-DAY", qty=1, rate=100, amount=100, charge_date="2026-06-18"),
			row(source_activity="med-1", activity_type="Medication", billing_status="Pending Invoice", item="MED-1", qty=1, rate=50, amount=50),
			row(source_activity="lab-1", activity_type="Lab", billing_status="Invoiced", item="LAB-1", qty=1, rate=70, amount=70),
			row(source_activity="old-1", activity_type="Manual", billing_status="Cancelled", item="OLD-1", qty=1, rate=20, amount=20),
			row(source_activity="missing-1", activity_type="Procedure", billing_status="Pending Invoice", item="PROC-1", qty=1, rate=0, amount=0),
		],
		activities=[
			row(name="ACT-1", activity_reference="med-1", activity_datetime="2026-06-20 08:00:00", billable=1, billing_status="Pending Charge", stock_affecting=0),
			row(name="ACT-2", activity_reference="stock-1", activity_datetime="2026-06-20 09:00:00", billable=0, billing_status="Not Billable", stock_affecting=1, stock_status="Pending", stock_entry=None),
		],
	)
	stub.hospitalisations["VHOS-002"] = make_hospitalisation("VHOS-002", status="Under Care", care_location="Ward A")
	stub.hospitalisations["VHOS-003"] = make_hospitalisation("VHOS-003", status="Discharged")
	stub.hospitalisations["VHOS-004"] = make_hospitalisation("VHOS-004", status="Cancelled")
	stub.locations["Ward A"] = row(name="Ward A", location_name="Ward A", branch="Main", location_type="Ward", status="Occupied", capacity=3, enabled=1)
	stub.logs = [
		row(name="LOG-1", hospitalisation="VHOS-001", patient="VP-1", care_location="Ward A", assigned_on="2026-06-18 09:00:00", status="Active"),
		row(name="LOG-2", hospitalisation="VHOS-002", patient="VP-2", care_location="Ward A", assigned_on="2026-06-19 09:00:00", status="Active"),
	]
	return stub


class TestHospitalisationReports(TestCase):
	def report_context(self, stub):
		return patch.multiple(
			reports,
			frappe=stub,
			build_hospitalisation_discharge_readiness=Mock(return_value={"can_discharge": False, "messages": ["Care location is still assigned"]}),
			now_datetime=Mock(return_value="2026-06-21 10:00:00"),
		)

	def test_active_hospitalisations_report_returns_active_records(self):
		stub = make_stub()
		with self.report_context(stub):
			_, data = reports.get_active_hospitalisations({})
		names = {row["hospitalisation"] for row in data}
		self.assertIn("VHOS-001", names)
		self.assertIn("VHOS-002", names)
		self.assertNotIn("VHOS-003", names)
		self.assertNotIn("VHOS-004", names)

	def test_status_filter_can_return_discharged_records(self):
		stub = make_stub()
		with self.report_context(stub):
			_, data = reports.get_active_hospitalisations({"status": "Discharged"})
		self.assertEqual([row["hospitalisation"] for row in data], ["VHOS-003"])

	def test_charge_summary_includes_daily_and_activity_charges(self):
		stub = make_stub()
		with self.report_context(stub):
			_, data = reports.get_hospitalisation_charge_report({"patient": "VP-1"})
		result = data[0]
		self.assertEqual(result["pending_charges"], 150)
		self.assertEqual(result["invoiced_charges"], 70)
		self.assertEqual(result["cancelled_charges"], 20)
		self.assertEqual(result["total_charges"], 240)

	def test_missing_price_count_is_correct(self):
		stub = make_stub()
		with self.report_context(stub):
			_, data = reports.get_hospitalisation_charge_report({"missing_price_only": 1})
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["missing_price_count"], 1)

	def test_care_location_occupancy_calculates_capacity_and_slots(self):
		stub = make_stub()
		with self.report_context(stub):
			_, data = reports.get_care_location_occupancy_report({"branch": "Main"})
		self.assertEqual(data[0]["capacity"], 3)
		self.assertEqual(data[0]["active_occupancy"], 2)
		self.assertEqual(data[0]["available_slots"], 1)
		self.assertEqual(data[0]["usage_indicator"], "Occupied")

	def test_discharge_watch_includes_long_stay_and_care_location_warning(self):
		stub = make_stub()
		with self.report_context(stub):
			_, data = reports.get_discharge_watch_report({"minimum_days_admitted": 1, "pending_issue_type": "Care Location Still Assigned"})
		names = {row["hospitalisation"] for row in data}
		self.assertIn("VHOS-001", names)
		self.assertTrue(any("Care location" in row["warning_summary"] for row in data))

	def test_pending_actions_include_stock_missing_price_and_charge_sync(self):
		stub = make_stub()
		with self.report_context(stub):
			_, data = reports.get_pending_hospitalisation_actions({"patient": "VP-1"})
		actions = {row["action_type"] for row in data}
		self.assertIn("Missing Price Charges", actions)
		self.assertIn("Pending Charge Sync", actions)
		self.assertIn("Pending Stock Posting", actions)

	def test_report_helpers_do_not_mutate_hospitalisation_modified_timestamp(self):
		stub = make_stub()
		before = {name: doc.modified for name, doc in stub.hospitalisations.items()}
		with self.report_context(stub):
			reports.get_active_hospitalisations({})
			reports.get_hospitalisation_charge_report({})
			reports.get_discharge_watch_report({"minimum_days_admitted": 1})
			reports.get_pending_hospitalisation_actions({})
			reports.get_care_location_occupancy_report({})
		after = {name: doc.modified for name, doc in stub.hospitalisations.items()}
		self.assertEqual(before, after)
		for doc in stub.hospitalisations.values():
			doc.save.assert_not_called()
		stub.db.set_value.assert_not_called()
