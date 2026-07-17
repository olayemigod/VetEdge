from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import hospitalisation, payment_gate


def doc(**values):
	row = frappe._dict(values)
	row.get = row.get
	row.set = lambda key, value: setattr(row, key, value)
	row.save = Mock()
	row.insert = Mock(side_effect=lambda **kwargs: setattr(row, "name", row.get("name") or "VHOS-001"))
	row.is_new = lambda: not bool(row.get("name"))
	return row


def meta(*fields):
	return SimpleNamespace(has_field=lambda fieldname: fieldname in fields)


def settings(
	enabled=1,
	gate="Partial Payment Gate",
	requires_consultation=1,
	allow_direct_admission=0,
	initial_billing_source="Linked Consultation Billing Session",
	admission_fee_item=None,
	admission_fee_uom=None,
):
	return frappe._dict(
		enable_veterinary_hospitalisation=enabled,
		hospitalisation_payment_gate=gate,
		hospitalisation_requires_consultation=requires_consultation,
		allow_direct_hospitalisation_admission=allow_direct_admission,
		hospitalisation_initial_billing_source=initial_billing_source,
		hospitalisation_admission_fee_item=admission_fee_item,
		hospitalisation_admission_fee_uom=admission_fee_uom,
	)


def invoice(docstatus=1, outstanding_amount=0, grand_total=1000, paid_amount=0, payments=None):
	return doc(
		doctype="Sales Invoice",
		name="SINV-001",
		docstatus=docstatus,
		outstanding_amount=outstanding_amount,
		grand_total=grand_total,
		paid_amount=paid_amount,
		payments=payments or [],
	)


class TestHospitalisationActions(TestCase):
	def test_feature_disabled_blocks_create_and_admit_server_side(self):
		frappe_stub = make_frappe_stub(settings_doc=settings(enabled=0))

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			self.assertRaises(
				frappe.ValidationError,
				hospitalisation.create_hospitalisation_from_consultation,
				"VCON-001",
			)
			self.assertRaises(frappe.ValidationError, hospitalisation.admit_hospitalisation, "VHOS-001")

		self.assertEqual(frappe_stub.throw.call_args.args[0], hospitalisation.DISABLED_MESSAGE)


	def test_admit_blocks_direct_hospitalisation_when_consultation_required(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", linked_consultation=None)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: hosp)

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			result = hospitalisation.admit_hospitalisation("VHOS-001")

		self.assertTrue(result["blocked"])
		self.assertTrue(result["reload_required"])
		self.assertIn("Hospitalisation should be created from a Consultation", result["message"])
		hosp.save.assert_not_called()

	def test_hospitalisation_patient_context_returns_owner_and_details(self):
		patient = doc(
			doctype="Veterinary Patient",
			name="VP-001",
			patient_name="Max",
			primary_owner="CUST-001",
			default_branch="Main",
			species="Canine",
			breed="Labrador",
			sex="Male",
			approximate_age="3 years",
			date_of_birth="2023-01-01",
		)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: patient)

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			context = hospitalisation.get_hospitalisation_patient_context("VP-001")

		self.assertEqual(context["customer"], "CUST-001")
		self.assertEqual(context["patient_name"], "Max")
		self.assertEqual(context["service_branch"], "Main")
		self.assertEqual(context["species"], "Canine")
		self.assertEqual(context["age"], "3 years")
		patient.save.assert_not_called()

	def test_hospitalisation_patient_context_missing_optional_fields_does_not_crash(self):
		patient = doc(doctype="Veterinary Patient", name="VP-002", patient_name="Tiny", primary_owner="CUST-002")
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: patient)

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			context = hospitalisation.get_hospitalisation_patient_context("VP-002")

		self.assertEqual(context["customer"], "CUST-002")
		self.assertEqual(context["patient_name"], "Tiny")
		self.assertIsNone(context["species"])
		self.assertIsNone(context["date_of_birth"])

	def test_hospitalisation_charge_summary_is_read_only(self):
		hospital_doc = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			sales_invoice="SINV-001",
			invoice_status="Draft",
			charge_items=[
				doc(name="CHG-1", amount=100, billing_status="Pending Invoice"),
				doc(name="CHG-2", amount=50, billing_status="Invoiced"),
				doc(name="CHG-3", amount=25, billing_status="Cancelled"),
			],
		)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: hospital_doc)

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			summary = hospitalisation.get_hospitalisation_charge_summary("VHOS-001")

		self.assertEqual(summary["total_pending"], 100)
		self.assertEqual(summary["total_invoiced"], 50)
		self.assertEqual(summary["total_cancelled"], 25)
		hospital_doc.save.assert_not_called()

	def test_hospitalisation_invoice_status_normalizes_billing_core_session_text(self):
		self.assertEqual(hospitalisation.get_hospitalisation_invoice_status(status="Draft Invoice Pending"), "Draft")
		self.assertEqual(hospitalisation.get_hospitalisation_invoice_status(status="Pending Invoice"), "Not Invoiced")
		self.assertEqual(hospitalisation.get_hospitalisation_invoice_status(status="Partially Paid"), "Partly Paid")

	def test_hospitalisation_draft_invoice_status_is_draft(self):
		invoice = doc(doctype="Sales Invoice", name="SINV-DRAFT", docstatus=0, outstanding_amount=100, grand_total=100)
		self.assertEqual(hospitalisation.get_hospitalisation_invoice_status(invoice), "Draft")

	def test_hospitalisation_js_contains_stabilised_action_flows(self):
		js_path = Path(__file__).resolve().parents[1] / "veterinary" / "doctype" / "veterinary_hospitalisation" / "veterinary_hospitalisation.js"
		script = js_path.read_text()
		self.assertIn("get_hospitalisation_stock_posting_preview", script)
		self.assertIn("Confirm Post", script)
		self.assertIn("open_medication_multi_row_dialog", script)
		self.assertIn("get_medication_dialog_table_fields", script)
		self.assertIn('fieldtype: "Table"', script)
		self.assertIn('options: "Item"', script)
		self.assertIn('options: "UOM"', script)
		self.assertIn("get_hospitalisation_medication_item_context", script)
		self.assertIn("Rate is required for billable medication", script)
		self.assertIn("append_charge_item_for_activity", script)
		self.assertIn("add_vaccination_activity_with_billing", script)
		self.assertIn("add_lab_activities_with_billing", script)
		self.assertIn("frm.reload_doc().then", script)

	def test_hospitalisation_final_status_keeps_history_billing_actions_visible(self):
		js_path = Path(__file__).resolve().parents[1] / "veterinary" / "doctype" / "veterinary_hospitalisation" / "veterinary_hospitalisation.js"
		script = js_path.read_text()

		self.assertIn('frm.add_custom_button(__("Billing / Payment")', script)
		self.assertIn('frm.add_custom_button(__("Check Payment Gate")', script)
		self.assertIn('frm.add_custom_button(__("View Charge Summary")', script)
		self.assertIn('if (["Cancelled", "Discharged"].includes(frm.doc.status))', script)
		self.assertIn('if (frm.is_new() || ["Cancelled", "Discharged"].includes(frm.doc.status))', script)

	def test_medication_item_context_uses_price_and_stock_defaults(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", company="Company A", customer="CUST-001", service_branch="Main")

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Item":
				return frappe._dict(item_name="Amoxicillin", stock_uom="Nos", is_stock_item=1, standard_rate=0)
			return None

		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: hosp)
		frappe_stub.db.get_value = get_value
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch("vetedge.services.billing_core._get_item_selling_rate", return_value=250),
		):
			context = hospitalisation.get_hospitalisation_medication_item_context("VHOS-001", "AMOX-001")

		self.assertEqual(context["item_name"], "Amoxicillin")
		self.assertEqual(context["uom"], "Nos")
		self.assertEqual(context["is_stock_item"], 1)
		self.assertEqual(context["rate"], 250)
		self.assertEqual(context["missing_price"], 0)

	def test_medication_item_context_reports_missing_price_for_non_stock_item(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001")

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Item":
				return frappe._dict(item_name="Clinical Advice", stock_uom="Unit", is_stock_item=0, standard_rate=0)
			return None

		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: hosp)
		frappe_stub.db.get_value = get_value
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch("vetedge.services.billing_core._get_item_selling_rate", return_value=0),
		):
			context = hospitalisation.get_hospitalisation_medication_item_context("VHOS-001", "ADVICE-001")

		self.assertEqual(context["is_stock_item"], 0)
		self.assertEqual(context["rate"], 0)
		self.assertEqual(context["missing_price"], 1)

	def test_create_hospitalisation_from_consultation_creates_linked_record(self):
		created = []
		consultation = doc(
			doctype="Veterinary Consultation",
			name="VCON-001",
			patient="VP-001",
			primary_owner="CUST-001",
			service_branch="Main",
			company="Company A",
			consulting_practitioner="vet@example.com",
			presenting_complaint="Needs inpatient care",
		)

		def get_doc(doctype, name=None):
			if isinstance(doctype, dict):
				new_doc = doc(**doctype, name="VHOS-001")
				new_doc.insert = Mock(side_effect=lambda **kwargs: created.append(new_doc))
				return new_doc
			return consultation

		frappe_stub = make_frappe_stub(get_doc=get_doc, get_all=Mock(return_value=[]))
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			name = hospitalisation.create_hospitalisation_from_consultation("VCON-001")

		self.assertEqual(name, "VHOS-001")
		self.assertEqual(created[0].linked_consultation, "VCON-001")
		self.assertEqual(created[0].patient, "VP-001")
		self.assertEqual(created[0].customer, "CUST-001")
		self.assertFalse(created[0].get("care_location"))

	def test_duplicate_active_hospitalisation_from_same_consultation_is_prevented(self):
		frappe_stub = make_frappe_stub(get_all=Mock(return_value=[frappe._dict(name="VHOS-EXISTING")]))
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
		):
			name = hospitalisation.create_hospitalisation_from_consultation("VCON-001")

		self.assertEqual(name, "VHOS-EXISTING")

	def test_hospitalisation_invoice_can_be_created_and_linked(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", sales_invoice=None)
		linked_invoice = invoice(docstatus=0, outstanding_amount=1000)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: linked_invoice if doctype == "Sales Invoice" else hosp)

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(hospitalisation, "sync_hospitalisation_charges_with_billing_core", return_value={"invoice": "SINV-001"}) as sync,
		):
			name = hospitalisation.create_or_link_hospitalisation_invoice("VHOS-001")

		self.assertEqual(name, "SINV-001")
		sync.assert_called_once_with("VHOS-001")

	def test_create_hospitalisation_invoice_doc_is_deprecated(self):
		frappe_stub = make_frappe_stub()
		with patch.object(hospitalisation, "frappe", frappe_stub):
			self.assertRaises(frappe.ValidationError, hospitalisation.create_hospitalisation_invoice_doc, doc(name="VHOS-001"))

	def test_admission_blocks_without_submitted_invoice(self):
		hosp = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			status="Draft",
			customer="CUST-001",
			patient="VP-001",
			company="Company A",
			linked_consultation="VCON-001",
			sales_invoice=None,
		)
		draft_invoice = invoice(docstatus=0, outstanding_amount=1000)
		session = billing_session()

		def get_doc(doctype, name=None):
			if doctype == "Sales Invoice":
				return draft_invoice
			if doctype == "Veterinary Billing Session":
				return session
			return hosp

		frappe_stub = make_frappe_stub(
			get_doc=get_doc,
			settings_doc=settings(requires_consultation=0, allow_direct_admission=1),
		)
		with billing_core_admit_context(
			frappe_stub,
			session,
			sync_result={"session": "VBS-001", "invoice": "SINV-001", "created": True},
			gate={"can_proceed": False, "status": "Blocked", "message": "At least one linked Sales Invoice must be submitted before service can proceed."},
		):
			with patch.object(hospitalisation, "create_hospitalisation_invoice_doc", side_effect=AssertionError("legacy invoice path called")):
				result = hospitalisation.admit_hospitalisation("VHOS-001")

		self.assertFalse(result["can_proceed"])
		self.assertEqual(result["billing_session"], "VBS-001")
		self.assertEqual(result["invoice"], "SINV-001")
		self.assertEqual(hosp.status, "Draft")
		self.assertEqual(hosp.payment_gate_status, "Blocked")
		self.assertEqual(hosp.sales_invoice, "SINV-001")

	def test_linked_consultation_billing_source_blocks_without_link_or_session(self):
		hosp = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			status="Draft",
			customer="CUST-001",
			patient="VP-001",
			linked_consultation=None,
			sales_invoice=None,
		)
		frappe_stub = make_frappe_stub(
			get_doc=lambda doctype, name=None: hosp,
			get_all=Mock(return_value=[]),
			settings_doc=settings(requires_consultation=0, allow_direct_admission=1),
		)
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session") as sync,
		):
			result = hospitalisation.admit_hospitalisation("VHOS-001")

		sync.assert_not_called()
		self.assertTrue(result["blocked"])
		self.assertIn("Link a Consultation", result["message"])
		self.assertEqual(hosp.status, "Draft")

	def test_admit_uses_billing_core_and_allows_when_gate_passes(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", linked_consultation="VCON-001", sales_invoice=None)
		paid_invoice = invoice(docstatus=1, outstanding_amount=0)
		session = billing_session(status="Paid")

		def get_doc(doctype, name=None):
			if doctype == "Sales Invoice":
				return paid_invoice
			if doctype == "Veterinary Billing Session":
				return session
			return hosp

		frappe_stub = make_frappe_stub(
			get_doc=get_doc,
			settings_doc=settings(requires_consultation=0, allow_direct_admission=1),
		)
		with billing_core_admit_context(
			frappe_stub,
			session,
			sync_result={"session": "VBS-001", "invoice": "SINV-PAID", "created": False},
			gate={"can_proceed": True, "status": "Allowed", "message": "Payment gate passed."},
		) as ctx:
			with patch.object(hospitalisation, "create_hospitalisation_invoice_doc", side_effect=AssertionError("legacy invoice path called")):
				result = hospitalisation.admit_hospitalisation("VHOS-001")

		ctx["sync"].assert_called_once_with("Veterinary Hospitalisation", "VHOS-001")
		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.status, "Admitted")
		self.assertEqual(hosp.admitted_by, "vet@example.com")
		self.assertEqual(hosp.payment_gate_status, "Allowed")

	def test_admit_refetches_after_billing_core_updates_hospitalisation(self):
		stale_hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", linked_consultation="VCON-001", sales_invoice=None)
		stale_hosp.save = Mock(side_effect=AssertionError("stale hospitalisation document saved"))
		gate_hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", linked_consultation="VCON-001", sales_invoice=None)
		admit_hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", linked_consultation="VCON-001", sales_invoice="SINV-001")
		paid_invoice = invoice(docstatus=1, outstanding_amount=0)
		session = billing_session(status="Paid")
		hospitalisation_docs = [stale_hosp, gate_hosp, admit_hosp]

		def get_doc(doctype, name=None):
			if doctype == "Sales Invoice":
				return paid_invoice
			if doctype == "Veterinary Billing Session":
				return session
			if doctype == "Veterinary Hospitalisation":
				return hospitalisation_docs.pop(0)
			return doc(doctype=doctype, name=name)

		def sync_side_effect(source_doctype, source_name):
			stale_hosp.invoice_status = "Draft"
			return {"session": "VBS-001", "invoice": "SINV-PAID", "created": False}

		frappe_stub = make_frappe_stub(
			get_doc=get_doc,
			settings_doc=settings(requires_consultation=0, allow_direct_admission=1),
		)
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", side_effect=sync_side_effect),
			patch("vetedge.services.billing_core.get_payment_gate_status", return_value={"can_proceed": True, "status": "Allowed", "message": "Payment gate passed."}),
			patch("vetedge.services.billing_core.get_billing_session_summary", return_value={"name": session.name}),
			patch.object(hospitalisation, "create_hospitalisation_invoice_doc", side_effect=AssertionError("legacy invoice path called")),
		):
			result = hospitalisation.admit_hospitalisation("VHOS-001")

		self.assertTrue(result["can_proceed"])
		self.assertTrue(result["reload_required"])
		self.assertEqual(result["status"], "Admitted")
		gate_hosp.save.assert_called_once()
		admit_hosp.save.assert_called_once()
		self.assertEqual(admit_hosp.status, "Admitted")
		self.assertEqual(admit_hosp.admitted_by, "vet@example.com")

	def test_admit_no_payment_gate_allows_after_billing_core_invoice_generation(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Draft", linked_consultation="VCON-001", sales_invoice=None)
		draft_invoice = invoice(docstatus=0, outstanding_amount=1000)
		session = billing_session(payment_gate_mode="No Payment Gate")

		def get_doc(doctype, name=None):
			if doctype == "Sales Invoice":
				return draft_invoice
			if doctype == "Veterinary Billing Session":
				return session
			return hosp

		frappe_stub = make_frappe_stub(
			get_doc=get_doc,
			settings_doc=settings(gate="No Payment Gate", requires_consultation=0, allow_direct_admission=1),
		)
		with billing_core_admit_context(
			frappe_stub,
			session,
			sync_result={"session": "VBS-001", "invoice": "SINV-DRAFT", "created": True},
			gate={"can_proceed": True, "status": "Allowed", "message": "Invoice has been generated. Payment is not required before proceeding."},
		):
			result = hospitalisation.admit_hospitalisation("VHOS-001")

		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.status, "Admitted")
		self.assertEqual(hosp.sales_invoice, "SINV-DRAFT")

	def test_draft_invoice_does_not_satisfy_any_gate(self):
		for gate in ("Full Payment Required", "Partial Payment Gate", "No Payment Gate"):
			with self.subTest(gate=gate):
				hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", sales_invoice="SINV-001")
				draft_invoice = invoice(docstatus=0, outstanding_amount=1000)
				frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: draft_invoice if doctype == "Sales Invoice" else hosp, settings_doc=settings(gate=gate))
				with hospitalisation_gate_context(frappe_stub, draft_invoice, gate=gate):
					result = hospitalisation.check_hospitalisation_payment_gate("VHOS-001")

				self.assertFalse(result["can_proceed"])
				self.assertEqual(hosp.payment_gate_status, "Blocked")

	def test_full_payment_required_blocks_unpaid_invoice(self):
		result, hosp = run_hospitalisation_gate("Full Payment Required", invoice(docstatus=1, outstanding_amount=1000))

		self.assertFalse(result["can_proceed"])
		self.assertEqual(hosp.payment_gate_status, "Blocked")

	def test_partial_payment_gate_allows_partially_paid_invoice(self):
		result, hosp = run_hospitalisation_gate(
			"Partial Payment Gate",
			invoice(docstatus=1, outstanding_amount=700, grand_total=1000),
			payment_rows=[frappe._dict(parent="PE-001", allocated_amount=300)],
		)

		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.payment_gate_status, "Allowed")

	def test_no_payment_gate_allows_submitted_unpaid_invoice(self):
		result, hosp = run_hospitalisation_gate("No Payment Gate", invoice(docstatus=1, outstanding_amount=1000))

		self.assertTrue(result["can_proceed"])
		self.assertEqual(hosp.payment_gate_status, "Allowed")

	def test_hospitalisation_title_includes_patient_date_and_admitting_vet(self):
		hosp = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			patient="VP-001",
			admission_datetime="2026-06-20 09:30:00",
			attending_veterinarian="vet@example.com",
		)
		frappe_stub = make_frappe_stub()
		frappe_stub.db.get_value.side_effect = lambda doctype, name, fieldname=None, **kwargs: {
			("Veterinary Patient", "VP-001", "patient_name"): "Max",
			("User", "vet@example.com", "full_name"): "Dr Ada Bello",
		}.get((doctype, name, fieldname))

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "formatdate", return_value="20 Jun 2026"),
		):
			hospitalisation.sync_hospitalisation_title(hosp)

		self.assertEqual(hosp.hospitalisation_title, "Max - 20 Jun 2026 - Dr Ada Bello - Hospitalisation")

	def test_discharge_sets_discharge_fields(self):
		hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", status="Under Care")
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: hosp)
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(hospitalisation, "now", return_value="2026-06-19 09:00:00"),
			patch.object(
				hospitalisation,
				"get_hospitalisation_discharge_billing_state",
				return_value=({"outstanding_amount": 0, "invoice_ledger": {}}, {"can_proceed": True, "status": "Allowed", "message": "Payment gate passed."}),
			),
		):
			result = hospitalisation.discharge_hospitalisation("VHOS-001", "Recovered")

		self.assertEqual(result["hospitalisation"], "VHOS-001")
		self.assertEqual(hosp.status, "Discharged")
		self.assertEqual(hosp.discharged_by, "vet@example.com")
		self.assertEqual(hosp.discharge_summary, "Recovered")

	def test_discharged_hospitalisation_preserves_history_links_and_references(self):
		charge_items = [
			doc(name="CHG-1", item="WARD-DAY", amount=5000, billing_status="Invoiced", sales_invoice="SINV-001"),
			doc(name="CHG-2", item="MED-001", amount=1200, billing_status="Invoiced", sales_invoice="SINV-001", source_activity="ACT-1"),
		]
		activities = [
			doc(name="ACT-1", activity_type="Medication", stock_entry="STE-001", notes="Medication administered"),
			doc(name="ACT-2", activity_type="Observation", notes="Stable overnight"),
		]
		hosp = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			status="Under Care",
			patient="VP-001",
			customer="CUST-001",
			linked_consultation="VCON-001",
			service_branch="Main Branch",
			care_location=None,
			care_location_history="Kennel A occupied from admission to release",
			sales_invoice="SINV-001",
			billing_session="VBS-001",
			stock_entry_reference="STE-001",
			charge_items=charge_items,
			activities=activities,
		)
		frappe_stub = make_frappe_stub(get_doc=lambda doctype, name=None: hosp)

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(hospitalisation, "now", return_value="2026-06-19 09:00:00"),
			patch.object(
				hospitalisation,
				"get_hospitalisation_discharge_billing_state",
				return_value=({"outstanding_amount": 0, "invoice_ledger": {"SINV-001": {"docstatus": 1}}}, {"can_proceed": True, "status": "Allowed", "message": "Payment gate passed."}),
			),
		):
			result = hospitalisation.discharge_hospitalisation("VHOS-001", "Recovered")

		self.assertEqual(result["hospitalisation"], "VHOS-001")
		self.assertEqual(hosp.status, "Discharged")
		self.assertEqual(hosp.patient, "VP-001")
		self.assertEqual(hosp.customer, "CUST-001")
		self.assertEqual(hosp.linked_consultation, "VCON-001")
		self.assertIsNone(hosp.care_location)
		self.assertEqual(hosp.care_location_history, "Kennel A occupied from admission to release")
		self.assertEqual(hosp.sales_invoice, "SINV-001")
		self.assertEqual(hosp.billing_session, "VBS-001")
		self.assertEqual(hosp.stock_entry_reference, "STE-001")
		self.assertEqual(hosp.charge_items, charge_items)
		self.assertEqual(hosp.activities, activities)

	def test_cancelled_hospitalisation_history_is_preserved_by_validation(self):
		charge_items = [doc(name="CHG-1", item="WARD-DAY", amount=5000, billing_status="Invoiced", sales_invoice="SINV-001")]
		activities = [doc(name="ACT-1", activity_type="Medication", stock_entry="STE-001")]
		hosp = doc(
			doctype="Veterinary Hospitalisation",
			name="VHOS-001",
			status="Cancelled",
			patient="VP-001",
			customer="CUST-001",
			linked_consultation="VCON-001",
			care_location="Kennel A",
			sales_invoice="SINV-001",
			billing_session="VBS-001",
			stock_entry_reference="STE-001",
			charge_items=charge_items,
			activities=activities,
		)
		frappe_stub = make_frappe_stub()

		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "is_hospitalisation_enabled", return_value=True),
		):
			hospitalisation.validate_hospitalisation(hosp)

		self.assertEqual(hosp.patient, "VP-001")
		self.assertEqual(hosp.customer, "CUST-001")
		self.assertEqual(hosp.linked_consultation, "VCON-001")
		self.assertEqual(hosp.care_location, "Kennel A")
		self.assertEqual(hosp.sales_invoice, "SINV-001")
		self.assertEqual(hosp.billing_session, "VBS-001")
		self.assertEqual(hosp.stock_entry_reference, "STE-001")
		self.assertEqual(hosp.charge_items, charge_items)
		self.assertEqual(hosp.activities, activities)


def run_hospitalisation_gate(gate, invoice_doc, payment_rows=None):
	hosp = doc(doctype="Veterinary Hospitalisation", name="VHOS-001", sales_invoice="SINV-001")
	frappe_stub = make_frappe_stub(
		get_doc=lambda doctype, name=None: invoice_doc if doctype == "Sales Invoice" else hosp,
		settings_doc=settings(gate=gate),
	)
	with hospitalisation_gate_context(frappe_stub, invoice_doc, gate=gate, payment_rows=payment_rows):
		result = hospitalisation.check_hospitalisation_payment_gate("VHOS-001")
	return result, hosp


def hospitalisation_gate_context(frappe_stub, invoice_doc, gate="Partial Payment Gate", payment_rows=None):
	from contextlib import contextmanager

	@contextmanager
	def manager():
		payment_frappe_stub = SimpleNamespace(
			db=SimpleNamespace(
				exists=lambda doctype, name=None: True,
				get_value=lambda doctype, name, fieldname=None, **kwargs: 1 if doctype == "Payment Entry" else None,
			),
			get_doc=lambda doctype, name=None: invoice_doc,
			get_all=lambda doctype, **kwargs: payment_rows or [],
			throw=Mock(side_effect=frappe.ValidationError),
			msgprint=Mock(),
			ValidationError=frappe.ValidationError,
		)
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch.object(payment_gate, "frappe", payment_frappe_stub),
		):
			yield

	return manager()


def billing_session(**values):
	defaults = {
		"doctype": "Veterinary Billing Session",
		"name": "VBS-001",
		"status": "Active",
		"payment_gate_mode": "Partial Payment Gate",
		"charges": [],
	}
	defaults.update(values)
	session = frappe._dict(defaults)
	session.save = Mock()
	return session


def billing_core_admit_context(frappe_stub, session, sync_result=None, gate=None):
	from contextlib import contextmanager

	@contextmanager
	def manager():
		sync_result = manager.sync_result or {"session": session.name, "invoice": "SINV-001", "created": True}
		gate_result = manager.gate or {"can_proceed": False, "status": "Blocked", "message": "Blocked"}
		with (
			patch.object(hospitalisation, "frappe", frappe_stub),
			patch.object(hospitalisation, "require_internal_user"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value=sync_result) as sync,
			patch("vetedge.services.billing_core.get_payment_gate_status", return_value=gate_result),
			patch("vetedge.services.billing_core.get_billing_session_summary", return_value={"name": session.name, "payment_gate": gate_result}),
		):
			yield {"sync": sync}

	manager.sync_result = sync_result
	manager.gate = gate
	return manager()


def make_frappe_stub(get_doc=None, get_all=None, settings_doc=None, item_exists=True):
	settings_doc = settings_doc or settings()
	get_doc = get_doc or (lambda doctype, name=None: doc(doctype=doctype, name=name))
	get_all = get_all or Mock(return_value=[])

	def exists(doctype, name=None):
		if doctype == "Item":
			return item_exists
		return True

	return SimpleNamespace(
		db=SimpleNamespace(exists=exists, get_value=Mock(return_value=None)),
		get_meta=lambda doctype: meta(
			"enable_veterinary_hospitalisation",
			"hospitalisation_payment_gate",
			"hospitalisation_requires_consultation",
			"allow_direct_hospitalisation_admission",
			"hospitalisation_initial_billing_source",
			"hospitalisation_admission_fee_item",
			"hospitalisation_admission_fee_uom",
			"branch",
		),
		get_single=lambda doctype: settings_doc,
		get_doc=get_doc,
		get_all=get_all,
		throw=Mock(side_effect=frappe.ValidationError),
		session=SimpleNamespace(user="vet@example.com"),
		ValidationError=frappe.ValidationError,
	)
