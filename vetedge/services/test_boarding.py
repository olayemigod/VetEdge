from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace


class ValidationError(Exception):
	pass


class FrappeDict(dict):
	def __getattr__(self, item):
		try:
			return self[item]
		except KeyError as exc:
			raise AttributeError(item) from exc

	def __setattr__(self, key, value):
		self[key] = value


MODULE_PATH = Path(__file__).resolve().parents[0] / "boarding.py"


def _to_date(value):
	if isinstance(value, date) and not isinstance(value, datetime):
		return value
	if isinstance(value, datetime):
		return value.date()
	return datetime.fromisoformat(str(value).replace(" ", "T")).date() if " " in str(value) else date.fromisoformat(str(value))


def load_boarding_module():
	frappe_module = types.ModuleType("frappe")
	frappe_module.ValidationError = ValidationError
	frappe_module.PermissionError = PermissionError
	frappe_module._dict = lambda value=None, **kwargs: FrappeDict(value or kwargs)
	frappe_module.session = SimpleNamespace(user="tester@example.com")
	frappe_module.db = SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=lambda *args, **kwargs: None, get_single_value=lambda *args, **kwargs: None)
	frappe_module.get_all = lambda *args, **kwargs: []
	frappe_module.whitelist = lambda fn=None, **kwargs: (fn if fn else (lambda inner: inner))

	def throw(message, exc=ValidationError):
		raise exc(message)

	frappe_module.throw = throw

	frappe_utils = types.ModuleType("frappe.utils")
	frappe_utils.date_diff = lambda end, start: (_to_date(end) - _to_date(start)).days
	frappe_utils.flt = lambda value: float(value or 0)
	frappe_utils.get_datetime = lambda value=None: datetime.fromisoformat(str(value).replace(" ", "T")) if value else datetime.now()
	frappe_utils.getdate = _to_date
	frappe_utils.now_datetime = lambda: datetime(2026, 5, 1, 9, 0, 0)
	frappe_utils.nowdate = lambda: "2026-05-01"

	sys.modules["frappe"] = frappe_module
	sys.modules["frappe.utils"] = frappe_utils

	billing_module = types.ModuleType("vetedge.services.billing")
	billing_module.PAID_STATUS = "Paid"
	billing_module.build_invoice_item = lambda *args, **kwargs: {}
	billing_module.get_invoice_payment_status = lambda invoice: "Paid" if getattr(invoice, "docstatus", 0) == 1 and float(getattr(invoice, "outstanding_amount", 0) or 0) <= 0 else "Unpaid"
	billing_module.is_active_sales_invoice = lambda *args, **kwargs: False
	billing_module.validate_sales_item = lambda *args, **kwargs: None
	feature_flags_module = types.ModuleType("vetedge.services.feature_flags")
	feature_flags_module.is_enabled = lambda name: True
	notifications_module = types.ModuleType("vetedge.services.notifications")
	notifications_module.emit_notification_event = lambda *args, **kwargs: {}
	portal_module = types.ModuleType("vetedge.services.portal_access")
	portal_module.require_internal_user = lambda: None
	registration_module = types.ModuleType("vetedge.services.registration_billing")
	registration_module.get_billing_cost_center = lambda *args, **kwargs: "Main - CC"
	registration_module.get_default_company = lambda: "VetEdge Co"

	sys.modules["vetedge.services.billing"] = billing_module
	sys.modules["vetedge.services.feature_flags"] = feature_flags_module
	sys.modules["vetedge.services.notifications"] = notifications_module
	sys.modules["vetedge.services.portal_access"] = portal_module
	sys.modules["vetedge.services.registration_billing"] = registration_module

	spec = importlib.util.spec_from_file_location("vetedge.services.boarding_test_module", MODULE_PATH)
	module = importlib.util.module_from_spec(spec)
	assert spec and spec.loader
	spec.loader.exec_module(module)
	return module


class BoardingAvailabilityHarness:
	def __init__(self, kennels=None, bookings=None, stays=None):
		self.module = load_boarding_module()
		self.kennels = kennels or []
		self.bookings = bookings or []
		self.stays = stays or []
		self.module.ensure_boarding_enabled = lambda: None
		self.module.frappe.get_all = self.get_all
		self.module.frappe.db.get_value = self.get_value

	def get_value(self, doctype, name, fields=None, as_dict=False):
		if doctype == self.module.KENNEL_DOCTYPE:
			for row in self.kennels:
				if row["name"] == name:
					if isinstance(fields, list):
						payload = {field: row.get(field) for field in fields}
						return self.module.frappe._dict(payload) if as_dict else payload
					return row.get(fields)
		return None

	def _matches_filters(self, row, filters):
		for key, expected in (filters or {}).items():
			value = row.get(key)
			if isinstance(expected, list) and expected and expected[0] == "in":
				if value not in expected[1]:
					return False
			elif value != expected:
				return False
		return True

	def _project(self, row, fields):
		if not fields:
			return self.module.frappe._dict(dict(row))
		return self.module.frappe._dict({field: row.get(field) for field in fields})

	def get_all(self, doctype, filters=None, fields=None, order_by=None, **kwargs):
		if doctype == self.module.KENNEL_DOCTYPE:
			rows = self.kennels
		elif doctype == self.module.PET_BOARDING_BOOKING_DOCTYPE:
			rows = self.bookings
		elif doctype == self.module.PET_BOARDING_STAY_DOCTYPE:
			rows = self.stays
		else:
			rows = []
		filtered = [row for row in rows if self._matches_filters(row, filters)]
		return [self._project(row, fields) for row in filtered]


class TestBoardingBusinessRulesDocumentation(unittest.TestCase):
	def test_same_day_boarding_is_one_billable_day(self):
		module = load_boarding_module()
		self.assertEqual(module.calculate_boarding_billable_days(date(2026, 5, 1), date(2026, 5, 1)), 1)

	def test_multi_day_boarding_is_inclusive(self):
		module = load_boarding_module()
		self.assertEqual(module.calculate_boarding_billable_days(date(2026, 5, 1), date(2026, 5, 3)), 3)


class TestKennelAvailabilityBoard(unittest.TestCase):
	def test_available_kennel_with_no_bookings(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 1, "is_active": 1}],
		)
		rows = harness.module.get_kennel_availability("Main Branch", "2026-05-01", "2026-05-07")
		self.assertEqual(rows[0].status, "Available")
		self.assertEqual(rows[0].available_slots, 1)

	def test_reserved_booking_blocks_availability(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 1, "is_active": 1}],
			bookings=[{"name": "PBB-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Reserved", "check_in_date": "2026-05-02", "expected_check_out_date": "2026-05-04", "actual_check_out_date": None}],
		)
		rows = harness.module.get_kennel_availability("Main Branch", "2026-05-02", "2026-05-03")
		self.assertEqual(rows[0].status, "Full")
		with self.assertRaises(ValidationError):
			harness.module.validate_kennel_available("KEN-1", "2026-05-02", "2026-05-03", service_branch="Main Branch")

	def test_active_stay_blocks_availability(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 2, "is_active": 1}],
			stays=[{"name": "PBS-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Active", "check_in_datetime": "2026-05-02 09:00:00", "check_out_datetime": "2026-05-05 11:00:00"}],
		)
		rows = harness.module.get_kennel_availability("Main Branch", "2026-05-03", "2026-05-03")
		self.assertEqual(rows[0].status, "Occupied")
		self.assertEqual(rows[0].available_slots, 1)

	def test_cancelled_booking_does_not_block_availability(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 1, "is_active": 1}],
			bookings=[{"name": "PBB-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Cancelled", "check_in_date": "2026-05-02", "expected_check_out_date": "2026-05-04", "actual_check_out_date": None}],
		)
		rows = harness.module.get_kennel_availability("Main Branch", "2026-05-02", "2026-05-03")
		self.assertEqual(rows[0].status, "Available")

	def test_checked_out_stay_does_not_block_availability(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 1, "is_active": 1}],
			stays=[{"name": "PBS-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Completed", "check_in_datetime": "2026-05-02 09:00:00", "check_out_datetime": "2026-05-02 17:00:00"}],
		)
		rows = harness.module.get_kennel_availability("Main Branch", "2026-05-03", "2026-05-04")
		self.assertEqual(rows[0].status, "Available")

	def test_capacity_greater_than_one_allows_multiple_bookings_until_full(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 2, "is_active": 1}],
			bookings=[
				{"name": "PBB-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Reserved", "check_in_date": "2026-05-02", "expected_check_out_date": "2026-05-04", "actual_check_out_date": None},
			],
		)
		row = harness.module.get_kennel_availability("Main Branch", "2026-05-02", "2026-05-03")[0]
		self.assertEqual(row.status, "Reserved")
		self.assertEqual(row.available_slots, 1)
		harness.module.validate_kennel_available("KEN-1", "2026-05-02", "2026-05-03", service_branch="Main Branch")
		harness.bookings.append({"name": "PBB-2", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Reserved", "check_in_date": "2026-05-02", "expected_check_out_date": "2026-05-04", "actual_check_out_date": None})
		row = harness.module.get_kennel_availability("Main Branch", "2026-05-02", "2026-05-03")[0]
		self.assertEqual(row.status, "Full")


	def test_default_boarding_daily_rate_fills_missing_booking_rate(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 1, "is_active": 1}],
		)
		harness.module.frappe.db.get_single_value = lambda doctype, field: {
			"default_boarding_billing_item": "BOARDING-SVC",
			"default_boarding_daily_rate": 4000,
		}.get(field)
		doc = SimpleNamespace(
			check_in_date="2026-05-01",
			expected_check_out_date="2026-05-03",
			actual_check_out_date=None,
			billing_item=None,
			daily_rate=None,
			billable_days=None,
			total_boarding_charge=None,
		)
		harness.module.validate_sales_item = lambda *args, **kwargs: None
		harness.module.frappe.db.get_value = lambda doctype, name, field, as_dict=False: 2500 if doctype == "Item" else None
		harness.module.sync_boarding_charge_fields(doc)
		self.assertEqual(doc.daily_rate, 4000.0)
		self.assertEqual(doc.billable_days, 3)
		self.assertEqual(doc.total_boarding_charge, 12000.0)


	def test_default_boarding_billing_item_fills_missing_booking_item(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 1, "is_active": 1}],
		)
		harness.module.frappe.db.get_single_value = lambda doctype, field: {
			"default_boarding_billing_item": "BOARDING-SVC",
			"default_boarding_daily_rate": None,
		}.get(field)
		doc = SimpleNamespace(
			check_in_date="2026-05-01",
			expected_check_out_date="2026-05-01",
			actual_check_out_date=None,
			billing_item=None,
			daily_rate=None,
			billable_days=None,
			total_boarding_charge=None,
		)
		harness.module.validate_sales_item = lambda *args, **kwargs: None
		harness.module.frappe.db.get_value = lambda doctype, name, field, as_dict=False: 2500 if doctype == "Item" else None
		harness.module.sync_boarding_charge_fields(doc)
		self.assertEqual(doc.billing_item, "BOARDING-SVC")
		self.assertEqual(doc.daily_rate, 2500)
		self.assertEqual(doc.billable_days, 1)
		self.assertEqual(doc.total_boarding_charge, 2500.0)


	def test_available_card_sums_available_slots_not_kennel_count(self):
		harness = BoardingAvailabilityHarness(
			kennels=[
				{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 3, "is_active": 1},
				{"name": "KEN-2", "kennel_name": "Suite B", "branch": "Main Branch", "capacity": 2, "is_active": 1},
			],
			bookings=[
				{"name": "PBB-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Reserved", "check_in_date": "2026-05-02", "expected_check_out_date": "2026-05-04", "actual_check_out_date": None},
			],
			stays=[
				{"name": "PBS-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Active", "check_in_datetime": "2026-05-02 09:00:00", "check_out_datetime": "2026-05-05 11:00:00"},
			],
		)
		rows = harness.module.get_kennel_availability("Main Branch", "2026-05-03", "2026-05-03")
		cards = harness.module.build_kennel_availability_board_cards(rows)
		available_card = next(card for card in cards if card["label"] == "Available")
		self.assertEqual(available_card["value"], 3)

	def test_check_in_blocks_when_payment_is_required_and_invoice_missing(self):
		module = load_boarding_module()
		module.ensure_boarding_enabled = lambda: None
		module.boarding_requires_payment_before_check_in = lambda: True
		module.validate_kennel_available = lambda *args, **kwargs: None
		module.create_boarding_stay_from_booking_doc = lambda doc: "PBS-1"
		module.emit_boarding_event = lambda *args, **kwargs: {}
		doc = SimpleNamespace(
			name="PBB-1",
			status="Reserved",
			check_in_date="2026-05-01",
			expected_check_out_date="2026-05-03",
			actual_check_out_date=None,
			service_branch="Main Branch",
			kennel="KEN-1",
			linked_stay=None,
			linked_invoice=None,
			save=lambda **kwargs: None,
		)
		with self.assertRaises(ValidationError):
			module.check_in_boarding_booking_doc(doc)


	def test_check_in_allows_paid_invoice_when_payment_is_required(self):
		module = load_boarding_module()
		module.ensure_boarding_enabled = lambda: None
		module.boarding_requires_payment_before_check_in = lambda: True
		module.validate_kennel_available = lambda *args, **kwargs: None
		module.create_boarding_stay_from_booking_doc = lambda doc: "PBS-1"
		module.emit_boarding_event = lambda *args, **kwargs: {}
		module.is_active_sales_invoice = lambda invoice_name: True
		module.frappe.get_doc = lambda doctype, name=None: SimpleNamespace(docstatus=1, outstanding_amount=0) if doctype == "Sales Invoice" else None
		saved = []
		doc = SimpleNamespace(
			name="PBB-1",
			status="Reserved",
			check_in_date="2026-05-01",
			expected_check_out_date="2026-05-03",
			actual_check_out_date=None,
			service_branch="Main Branch",
			kennel="KEN-1",
			linked_stay=None,
			linked_invoice="SINV-1",
			save=lambda **kwargs: saved.append(kwargs),
		)
		result = module.check_in_boarding_booking_doc(doc)
		self.assertEqual(result["status"], "Checked In")
		self.assertEqual(result["stay"], "PBS-1")
		self.assertEqual(doc.status, "Checked In")
		self.assertTrue(saved)


	def test_create_boarding_invoice_updates_existing_draft_days(self):
		module = load_boarding_module()
		module.calculate_boarding_charges = lambda doc: {"daily_rate": 2500, "billable_days": 3, "total_boarding_charge": 7500}
		module.get_billing_cost_center = lambda *args, **kwargs: "Main - CC"
		module.get_boarding_invoice_documents = lambda doc: [SimpleNamespace(name="SINV-DRAFT", docstatus=0)]
		module.build_boarding_invoice_item = lambda doc, cc: {"item_code": "BOARDING-SVC", "qty": doc.billable_days, "rate": doc.daily_rate, "amount": doc.total_boarding_charge, "cost_center": cc}
		module.update_draft_boarding_invoice = lambda invoice_name, doc, item_payload, cost_center: SimpleNamespace(name=invoice_name)
		saved = []
		doc = SimpleNamespace(
			name="PBB-1",
			status="Reserved",
			service_branch="Main Branch",
			primary_owner="CUST-1",
			billing_item="BOARDING-SVC",
			daily_rate=None,
			billable_days=None,
			total_boarding_charge=None,
			linked_invoice="SINV-DRAFT",
			get=lambda fieldname, default=None: getattr(doc, fieldname, default),
			save=lambda **kwargs: saved.append(kwargs),
		)
		result = module.create_boarding_invoice_doc(doc)
		self.assertEqual(result["invoice"], "SINV-DRAFT")
		self.assertFalse(result["created"])
		self.assertEqual(doc.billable_days, 3)
		self.assertEqual(doc.total_boarding_charge, 7500)
		self.assertTrue(saved)


	def test_create_boarding_invoice_creates_balance_invoice_for_submitted_days_delta(self):
		module = load_boarding_module()
		module.calculate_boarding_charges = lambda doc: {"daily_rate": 2500, "billable_days": 4, "total_boarding_charge": 10000}
		module.get_billing_cost_center = lambda *args, **kwargs: "Main - CC"
		prior_invoice = SimpleNamespace(
			name="SINV-OLD",
			docstatus=1,
			items=[SimpleNamespace(item_code="BOARDING-SVC", qty=2, rate=2500, amount=5000)],
		)
		module.get_boarding_invoice_documents = lambda doc: [prior_invoice]
		module.build_invoice_item = lambda item_code, qty, uom, rate, cost_center: {"item_code": item_code, "qty": qty, "rate": rate, "amount": qty * rate, "cost_center": cost_center}
		created = []
		module.create_boarding_sales_invoice = lambda doc, item_payload, cost_center, adjustment=False: created.append({"item_payload": item_payload, "cost_center": cost_center, "adjustment": adjustment}) or SimpleNamespace(name="SINV-BAL")
		module.emit_boarding_event = lambda *args, **kwargs: {}
		saved = []
		doc = SimpleNamespace(
			name="PBB-1",
			status="Checked Out",
			service_branch="Main Branch",
			primary_owner="CUST-1",
			billing_item="BOARDING-SVC",
			daily_rate=None,
			billable_days=None,
			total_boarding_charge=None,
			linked_invoice="SINV-OLD",
			get=lambda fieldname, default=None: getattr(doc, fieldname, default),
			save=lambda **kwargs: saved.append(kwargs),
		)
		result = module.create_boarding_invoice_doc(doc)
		self.assertEqual(result["invoice"], "SINV-BAL")
		self.assertTrue(result["created"])
		self.assertTrue(result["adjustment"])
		self.assertEqual(created[0]["item_payload"]["qty"], 2)
		self.assertEqual(created[0]["item_payload"]["rate"], 2500)
		self.assertTrue(saved)


	def test_check_out_blocks_when_invoice_has_not_been_created(self):
		module = load_boarding_module()
		module.ensure_boarding_enabled = lambda: None
		module.get_existing_active_stay = lambda name: "PBS-1"
		module.get_boarding_invoice_documents = lambda doc: []
		module.calculate_boarding_charges = lambda doc: {"daily_rate": 2500, "billable_days": 3, "total_boarding_charge": 7500}
		doc = SimpleNamespace(
			name="PBB-1",
			status="Checked In",
			actual_check_out_date=None,
			linked_stay=None,
			daily_rate=None,
			billable_days=None,
			total_boarding_charge=None,
		)
		with self.assertRaises(ValidationError):
			module.check_out_boarding_booking_doc(doc)


	def test_check_out_blocks_when_billing_no_longer_matches_extended_stay(self):
		module = load_boarding_module()
		module.ensure_boarding_enabled = lambda: None
		module.get_existing_active_stay = lambda name: "PBS-1"
		module.calculate_boarding_charges = lambda doc: {"daily_rate": 2500, "billable_days": 4, "total_boarding_charge": 10000}
		module.get_boarding_invoice_documents = lambda doc: [SimpleNamespace(docstatus=1, outstanding_amount=0, grand_total=5000, items=[SimpleNamespace(item_code="BOARDING-SVC", qty=2, rate=2500, amount=5000)])]
		doc = SimpleNamespace(
			name="PBB-1",
			status="Checked In",
			actual_check_out_date=None,
			linked_stay=None,
			billing_item="BOARDING-SVC",
			daily_rate=None,
			billable_days=None,
			total_boarding_charge=None,
		)
		with self.assertRaises(ValidationError):
			module.check_out_boarding_booking_doc(doc)


	def test_check_out_blocks_when_any_invoice_is_unpaid(self):
		module = load_boarding_module()
		module.ensure_boarding_enabled = lambda: None
		module.get_existing_active_stay = lambda name: "PBS-1"
		module.calculate_boarding_charges = lambda doc: {"daily_rate": 2500, "billable_days": 2, "total_boarding_charge": 5000}
		module.get_boarding_invoice_documents = lambda doc: [SimpleNamespace(docstatus=1, outstanding_amount=1000, grand_total=5000, items=[SimpleNamespace(item_code="BOARDING-SVC", qty=2, rate=2500, amount=5000)])]
		doc = SimpleNamespace(
			name="PBB-1",
			status="Checked In",
			actual_check_out_date=None,
			linked_stay=None,
			billing_item="BOARDING-SVC",
			daily_rate=None,
			billable_days=None,
			total_boarding_charge=None,
		)
		with self.assertRaises(ValidationError):
			module.check_out_boarding_booking_doc(doc)

	def test_inactive_kennel_is_unavailable(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 3, "is_active": 0}],
		)
		row = harness.module.get_kennel_availability("Main Branch", "2026-05-02", "2026-05-03")[0]
		self.assertEqual(row.status, "Out of Service / Inactive")
		with self.assertRaises(ValidationError):
			harness.module.validate_kennel_available("KEN-1", "2026-05-02", "2026-05-03", service_branch="Main Branch")

	def test_date_overlap_logic_only_counts_overlapping_records(self):
		harness = BoardingAvailabilityHarness(
			kennels=[{"name": "KEN-1", "kennel_name": "Suite A", "branch": "Main Branch", "capacity": 2, "is_active": 1}],
			bookings=[
				{"name": "PBB-1", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Reserved", "check_in_date": "2026-05-01", "expected_check_out_date": "2026-05-01", "actual_check_out_date": None},
				{"name": "PBB-2", "kennel": "KEN-1", "service_branch": "Main Branch", "status": "Reserved", "check_in_date": "2026-05-03", "expected_check_out_date": "2026-05-05", "actual_check_out_date": None},
			],
		)
		row = harness.module.get_kennel_availability("Main Branch", "2026-05-02", "2026-05-02")[0]
		self.assertEqual(row.current_occupancy, 0)
		row = harness.module.get_kennel_availability("Main Branch", "2026-05-03", "2026-05-03")[0]
		self.assertEqual(row.current_occupancy, 1)
