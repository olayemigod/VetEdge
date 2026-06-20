from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation


def row(**values):
	data = frappe._dict(values)
	data.get = data.get
	return data


def hosp(**values):
	defaults = {
		"doctype": "Veterinary Hospitalisation",
		"name": "VHOS-001",
		"status": "Under Care",
		"discharge_summary": None,
		"payment_gate_status": "Blocked",
		"payment_gate_message": "Still blocked",
		"activities": [],
		"charge_items": [],
	}
	defaults.update(values)
	doc = frappe._dict(defaults)
	doc.get = doc.get
	doc.set = lambda key, value: setattr(doc, key, value)
	doc.save = Mock()
	return doc


def billing_summary(outstanding=0, has_pending=False, draft=False, paid=100, submitted=1):
	return {
		"name": "VBS-001",
		"outstanding_amount": outstanding,
		"total_paid": paid,
		"payment_status": "Paid" if outstanding == 0 else "Partly Paid",
		"current_draft_invoice": "SINV-DRAFT" if draft else None,
		"latest_invoice": "SINV-001",
		"invoices": [{"name": "SINV-001", "docstatus": 1, "outstanding_amount": outstanding}],
		"invoice_ledger": {
			"has_pending_uninvoiced_charges": has_pending,
			"has_active_draft_invoice": draft,
			"outstanding_amount": outstanding,
			"submitted_invoice_count": submitted,
		},
	}


def gate(mode="Full Payment Required", allowed=True, message="Payment gate passed."):
	return {"gate": mode, "can_proceed": allowed, "status": "Allowed" if allowed else "Blocked", "message": message}


class TestHospitalisationDischarge(TestCase):
	def test_readiness_returns_missing_discharge_summary_requirement(self):
		doc = hosp()
		with discharge_context(doc, billing_summary(), gate()):
			result = hospitalisation.get_hospitalisation_discharge_readiness("VHOS-001")
		self.assertFalse(result["can_discharge"])
		self.assertIn("Complete Discharge Summary", result["recommended_actions"])

	def test_readiness_detects_pending_billable_activities_without_charge_items(self):
		doc = hosp(discharge_summary="Done", activities=[row(name="ACT-1", billable=1, billing_status="Pending Charge", activity_type="Medication")])
		with discharge_context(doc, billing_summary(), gate()):
			result = hospitalisation.get_hospitalisation_discharge_readiness("VHOS-001")
		self.assertEqual(len(result["pending_billable_activities"]), 1)
		self.assertIn("Build Charge Sheet", result["recommended_actions"])

	def test_readiness_detects_pending_charge_items_not_invoiced(self):
		doc = hosp(discharge_summary="Done", charge_items=[row(name="CHG-1", source_activity="ACT-1", billing_status="Pending Invoice", item="ITEM", amount=10)])
		with discharge_context(doc, billing_summary(), gate()):
			result = hospitalisation.get_hospitalisation_discharge_readiness("VHOS-001")
		self.assertEqual(len(result["pending_charge_items"]), 1)
		self.assertIn("Sync Charges to Invoice", result["recommended_actions"])

	def test_readiness_detects_pending_stock_affecting_activities_not_posted(self):
		doc = hosp(discharge_summary="Done", activities=[row(name="ACT-1", stock_affecting=1, stock_status="Pending", activity_type="Medication")])
		with discharge_context(doc, billing_summary(), gate()):
			result = hospitalisation.get_hospitalisation_discharge_readiness("VHOS-001")
		self.assertEqual(len(result["pending_stock_activities"]), 1)
		self.assertIn("Post Stock Usage", result["recommended_actions"])
		self.assertTrue(result["can_discharge"])

	def test_discharge_blocks_cancelled_hospitalisation(self):
		doc = hosp(status="Cancelled")
		with discharge_context(doc, billing_summary(), gate()):
			self.assertRaises(frappe.ValidationError, hospitalisation.discharge_hospitalisation, "VHOS-001", "Done")

	def test_discharge_blocks_already_discharged_hospitalisation(self):
		doc = hosp(status="Discharged")
		with discharge_context(doc, billing_summary(), gate()):
			self.assertRaises(frappe.ValidationError, hospitalisation.discharge_hospitalisation, "VHOS-001", "Done")

	def test_discharge_requires_summary_or_details(self):
		doc = hosp()
		with discharge_context(doc, billing_summary(), gate()):
			self.assertRaises(frappe.ValidationError, hospitalisation.discharge_hospitalisation, "VHOS-001")

	def test_full_payment_required_blocks_unpaid_session(self):
		doc = hosp()
		with discharge_context(doc, billing_summary(outstanding=50, paid=50), gate("Full Payment Required", False, "Full payment required.")):
			self.assertRaises(frappe.ValidationError, hospitalisation.discharge_hospitalisation, "VHOS-001", "Done")
		self.assertNotEqual(doc.status, "Discharged")

	def test_full_payment_required_allows_when_session_cleared(self):
		doc = hosp()
		with discharge_context(doc, billing_summary(outstanding=0), gate("Full Payment Required", True)):
			result = hospitalisation.discharge_hospitalisation("VHOS-001", "Done")
		self.assertEqual(result["status"], "Discharged")
		self.assertEqual(doc.discharge_billing_status, "Cleared")

	def test_partial_payment_gate_allows_with_warning(self):
		doc = hosp()
		with discharge_context(doc, billing_summary(outstanding=75, paid=25), gate("Partial Payment Gate", True, "This billing session still has unpaid balance from earlier invoice(s).")):
			hospitalisation.discharge_hospitalisation("VHOS-001", "Done")
		self.assertEqual(doc.status, "Discharged")
		self.assertEqual(doc.discharge_billing_status, "Partially Paid")
		self.assertIn("unpaid balance", doc.discharge_message)

	def test_no_payment_gate_allows_with_outstanding_warning(self):
		doc = hosp()
		with discharge_context(doc, billing_summary(outstanding=100, paid=0), gate("No Payment Gate", True, "This billing session still has unpaid balance from earlier invoice(s).")):
			hospitalisation.discharge_hospitalisation("VHOS-001", "Done")
		self.assertEqual(doc.status, "Discharged")
		self.assertEqual(doc.discharge_billing_status, "Partially Paid")

	def test_discharge_does_not_mutate_submitted_sales_invoice(self):
		doc = hosp()
		invoice = row(name="SINV-001", docstatus=1, outstanding_amount=0, save=Mock(), submit=Mock())
		with discharge_context(doc, billing_summary(), gate(), invoice=invoice):
			hospitalisation.discharge_hospitalisation("VHOS-001", "Done")
		invoice.save.assert_not_called()
		invoice.submit.assert_not_called()

	def test_discharge_does_not_post_stock_or_build_charge_sheet(self):
		doc = hosp(activities=[row(name="ACT-1", stock_affecting=1, stock_status="Pending")])
		with discharge_context(doc, billing_summary(), gate()):
			with patch.object(hospitalisation, "post_hospitalisation_activity_stock", side_effect=AssertionError("stock posted")), patch.object(hospitalisation, "build_hospitalisation_charge_items", side_effect=AssertionError("charge sheet built")):
				hospitalisation.discharge_hospitalisation("VHOS-001", "Done")
		self.assertEqual(doc.status, "Discharged")

	def test_discharge_sets_fields(self):
		doc = hosp()
		details = {"discharge_summary": "Recovered well", "condition_at_discharge": "Stable", "discharge_instructions": "Rest", "follow_up_date": "2026-07-01", "follow_up_notes": "Review"}
		with discharge_context(doc, billing_summary(), gate()):
			with patch.object(hospitalisation, "now", return_value="2026-06-20 10:00:00"):
				hospitalisation.discharge_hospitalisation("VHOS-001", discharge_details=details)
		self.assertEqual(doc.status, "Discharged")
		self.assertEqual(doc.discharged_by, "vet@example.com")
		self.assertEqual(doc.discharge_datetime, "2026-06-20 10:00:00")
		self.assertEqual(doc.discharge_summary, "Recovered well")
		self.assertEqual(doc.condition_at_discharge, "Stable")


class discharge_context:
	def __init__(self, doc, summary, gate_result, invoice=None):
		self.doc = doc
		self.summary = summary
		self.gate_result = gate_result
		self.invoice = invoice or row(name="SINV-001", docstatus=1, outstanding_amount=0)

	def __enter__(self):
		frappe_stub = SimpleNamespace(
			get_doc=lambda doctype, name=None: self.doc if doctype == "Veterinary Hospitalisation" else self.invoice,
			db=SimpleNamespace(exists=lambda doctype, name=None: True),
			throw=Mock(side_effect=frappe.ValidationError),
			ValidationError=frappe.ValidationError,
			session=SimpleNamespace(user="vet@example.com"),
			parse_json=frappe.parse_json,
		)
		self.patchers = [
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(hospitalisation, "get_hospitalisation_discharge_billing_state", return_value=(self.summary, self.gate_result)),
		]
		for patcher in self.patchers:
			patcher.start()
		return self

	def __exit__(self, exc_type, exc, tb):
		for patcher in reversed(self.patchers):
			patcher.stop()
