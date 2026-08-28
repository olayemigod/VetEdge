from __future__ import annotations

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from vetedge import qa_inspection


class TestQAInspection(FrappeTestCase):
	def _hospitalisation(self):
		return frappe._dict(
			name="VHOS-TEST-0001",
			status="Under Care",
			service_branch="Main Branch",
			company="Test Company",
			care_level="Standard",
			invoice_status="Unpaid",
			payment_gate_status="Blocked",
			payment_gate_message="Payment required",
			discharge_billing_status="Unpaid",
			discharge_message="Outstanding amount remains",
			patient="VPAT-SECRET",
			patient_name="Private Patient Name",
			customer="CUST-SECRET",
			charge_items=[
				frappe._dict(
					name="CHG-1",
					charge_category="Daily Stay",
					charge_date="2026-08-28",
					activity_type="Daily Stay",
					item="HOSP-DAY",
					qty=1,
					uom="Nos",
					rate=5000,
					amount=5000,
					billing_status="Invoiced",
					sales_invoice="SINV-TEST-1",
					pricing_source="Price List",
					source_key="daily::VHOS-TEST-0001::2026-08-28",
				),
			],
			activities=[
				frappe._dict(
					name="ACT-1",
					activity_reference="ACTREF-1",
					activity_datetime="2026-08-28 10:00:00",
					activity_type="Medication",
					clinical_notes="Sensitive clinical narrative must never leave VetEdge",
					billable=1,
					billing_status="Charged",
					item="DRUG-1",
					qty=2,
					uom="Nos",
					stock_affecting=1,
					stock_status="Posted",
					stock_entry="STE-TEST-1",
					posted_stock_qty=2,
					linked_doctype="Veterinary Consultation",
					linked_document="VCON-TEST-1",
				),
			],
		)

	def test_inspect_fails_closed_when_qa_environment_is_disabled(self):
		with patch.object(qa_inspection, "_assert_qa_environment", side_effect=frappe.PermissionError("disabled")):
			with self.assertRaises(frappe.PermissionError):
				qa_inspection.inspect("hospitalisation_charges", "VHOS-TEST-0001")

	def test_inspect_rejects_invalid_service_credential(self):
		with (
			patch.object(qa_inspection, "_assert_qa_environment"),
			patch.object(qa_inspection, "_assert_service_token", side_effect=frappe.PermissionError("invalid")),
		):
			with self.assertRaises(frappe.PermissionError):
				qa_inspection.inspect("hospitalisation_charges", "VHOS-TEST-0001")

	def test_inspect_rejects_unknown_inspection_type_before_provider_execution(self):
		with (
			patch.object(qa_inspection, "_assert_qa_environment"),
			patch.object(qa_inspection, "_assert_service_token", return_value="token"),
			patch.object(qa_inspection, "_rate_limit"),
			patch.object(qa_inspection, "_hospitalisation") as hospitalisation,
		):
			with self.assertRaises(frappe.ValidationError):
				qa_inspection.inspect("arbitrary_sql", "VHOS-TEST-0001")
			hospitalisation.assert_not_called()

	def test_charge_summary_contains_financial_evidence_without_owner_or_patient_identity(self):
		payload = qa_inspection._charge_summary(self._hospitalisation())
		self.assertEqual(payload["hospitalisation"], "VHOS-TEST-0001")
		self.assertEqual(payload["count"], 1)
		self.assertEqual(payload["total_amount"], 5000)
		self.assertEqual(payload["charges"][0]["sales_invoice"], "SINV-TEST-1")
		self.assertNotIn("patient", payload)
		self.assertNotIn("patient_name", payload)
		self.assertNotIn("customer", payload)

	def test_activity_summary_omits_clinical_notes_and_person_identity(self):
		payload = qa_inspection._activity_summary(self._hospitalisation())
		self.assertEqual(payload["count"], 1)
		self.assertEqual(payload["activities"][0]["activity_type"], "Medication")
		self.assertNotIn("clinical_notes", payload["activities"][0])
		self.assertNotIn("performed_by", payload["activities"][0])
		self.assertNotIn("patient", payload)
		self.assertNotIn("customer", payload)

	def test_invoice_summary_is_read_only_and_returns_only_fixed_accounting_fields(self):
		doc = self._hospitalisation()
		with (
			patch.object(qa_inspection.frappe.db, "exists", return_value=True),
			patch.object(
				qa_inspection.frappe.db,
				"get_value",
				return_value=frappe._dict(
					name="SINV-TEST-1",
					docstatus=1,
					status="Unpaid",
					posting_date="2026-08-28",
					company="Test Company",
					grand_total=5000,
					outstanding_amount=5000,
				),
			) as get_value,
		):
			payload = qa_inspection._invoice_summary(doc)
		self.assertEqual(payload["invoices"][0]["docstatus"], 1)
		self.assertEqual(payload["invoices"][0]["outstanding_amount"], 5000)
		get_value.assert_called_once()

	def test_stock_summary_reports_posting_state_without_stock_entry_items_or_patient_data(self):
		doc = self._hospitalisation()
		with (
			patch.object(qa_inspection.frappe.db, "exists", return_value=True),
			patch.object(
				qa_inspection.frappe.db,
				"get_value",
				return_value=frappe._dict(
					docstatus=1,
					purpose="Material Issue",
					posting_date="2026-08-28",
					posting_time="10:01:00",
					company="Test Company",
				),
			),
		):
			payload = qa_inspection._stock_summary(doc)
		self.assertEqual(payload["count"], 1)
		self.assertEqual(payload["stock_postings"][0]["stock_entry_docstatus"], 1)
		self.assertEqual(payload["stock_postings"][0]["posted_stock_qty"], 2)
		self.assertNotIn("items", payload["stock_postings"][0])
		self.assertNotIn("patient", payload)

	def test_authorized_inspection_dispatches_only_fixed_provider(self):
		doc = self._hospitalisation()
		with (
			patch.object(qa_inspection, "_assert_qa_environment"),
			patch.object(qa_inspection, "_assert_service_token", return_value="token"),
			patch.object(qa_inspection, "_rate_limit"),
			patch.object(qa_inspection, "_hospitalisation", return_value=doc),
			patch.object(qa_inspection, "_audit") as audit,
		):
			payload = qa_inspection.inspect("hospitalisation_activities", doc.name)
		self.assertEqual(payload["hospitalisation"], doc.name)
		audit.assert_called_once_with("hospitalisation_activities", doc.name)
