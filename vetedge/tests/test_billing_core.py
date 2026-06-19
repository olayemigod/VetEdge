from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import billing, billing_core, billing_modal, boarding, grooming, lab, registration_billing, vaccination


def make_session(**values):
	defaults = {
		"doctype": billing_core.BILLING_SESSION_DOCTYPE,
		"name": "VBS-001",
		"customer": "CUST-001",
		"animal": "PAT-001",
		"company": "Company A",
		"branch": "Main",
		"status": "Active",
		"payment_gate_mode": "Full Payment Gate",
		"current_draft_invoice": None,
		"latest_invoice": None,
		"total_charges": 0,
		"total_invoiced": 0,
		"total_paid": 0,
		"outstanding_amount": 0,
		"payment_status": "Not Invoiced",
		"charges": [],
	}
	defaults.update(values)
	session = frappe._dict(defaults)
	session.append = lambda fieldname, row: session.setdefault(fieldname, []).append(frappe._dict(row)) or session[fieldname][-1]
	session.save = Mock()
	return session


def make_invoice(name="SINV-001", docstatus=0, items=None, outstanding_amount=100):
	invoice = frappe._dict(
		doctype="Sales Invoice",
		name=name,
		docstatus=docstatus,
		status="Draft" if docstatus == 0 else "Unpaid",
		customer="CUST-001",
		company="Company A",
		branch="Main",
		grand_total=100,
		paid_amount=0,
		outstanding_amount=outstanding_amount,
		currency="NGN",
		items=items or [],
	)
	invoice.append = lambda fieldname, row: invoice.setdefault(fieldname, []).append(frappe._dict(row)) or invoice[fieldname][-1]
	invoice.insert = Mock()
	invoice.save = Mock()
	return invoice


def charge_payload(key="consultation-fee", item="ITEM-001", amount=100):
	return {
		"source_doctype": "Veterinary Consultation",
		"source_name": "VCON-001",
		"source_detail_name": key,
		"charge_key": key,
		"item_code": item,
		"item_name": item,
		"description": "Charge",
		"qty": 1,
		"rate": amount,
		"amount": amount,
		"cost_center": "CC-Main",
		"branch": "Main",
	}


class TestBillingCore(TestCase):
	def test_add_or_update_session_charge_is_idempotent(self):
		session = make_session()

		first = billing_core.add_or_update_session_charge(session, charge_payload())
		second = billing_core.add_or_update_session_charge(session, charge_payload(amount=125))

		self.assertIs(first, second)
		self.assertEqual(len(session.charges), 1)
		self.assertEqual(session.charges[0].amount, 125)

	def test_submitted_charge_is_not_mutated_by_charge_sync(self):
		session = make_session(charges=[frappe._dict({**charge_payload(), "billing_status": "Submitted Invoiced", "amount": 100})])

		row = billing_core.add_or_update_session_charge(session, charge_payload(amount=250))

		self.assertEqual(row.amount, 100)
		self.assertEqual(row.billing_status, "Submitted Invoiced")

	def test_invoice_sync_does_not_duplicate_invoice_items(self):
		session = make_session(current_draft_invoice="SINV-001", charges=[])
		billing_core.add_or_update_session_charge(session, charge_payload())
		invoice = make_invoice(items=[frappe._dict({"description": "Charge\nVetEdge billing charge: consultation-fee"})])

		with billing_core_context(session, invoice):
			result = billing_core.sync_session_charges_to_invoice(session)

		self.assertEqual(result["added_count"], 0)
		self.assertEqual(result["updated_count"], 1)
		self.assertEqual(len(invoice.get("items")), 1)

	def test_submitted_current_invoice_creates_new_draft_for_new_charge(self):
		session = make_session(current_draft_invoice="SINV-SUB", latest_invoice="SINV-SUB", charges=[])
		billing_core.add_or_update_session_charge(session, charge_payload("new-consultation-fee"))
		submitted = make_invoice("SINV-SUB", docstatus=1)
		new_invoice = make_invoice("SINV-NEW", docstatus=0)

		with billing_core_context(session, submitted, created_invoice=new_invoice):
			invoice, created = billing_core.create_or_update_draft_invoice_for_session(session)

		self.assertTrue(created)
		self.assertEqual(invoice.name, "SINV-NEW")
		self.assertEqual(session.current_draft_invoice, "SINV-NEW")

	def test_cancelled_current_invoice_creates_new_draft_for_new_charge(self):
		session = make_session(current_draft_invoice="SINV-CAN", latest_invoice="SINV-CAN", charges=[])
		billing_core.add_or_update_session_charge(session, charge_payload("new-consultation-fee"))
		cancelled = make_invoice("SINV-CAN", docstatus=2)
		new_invoice = make_invoice("SINV-NEW", docstatus=0)

		with billing_core_context(session, cancelled, created_invoice=new_invoice):
			invoice, created = billing_core.create_or_update_draft_invoice_for_session(session)

		self.assertTrue(created)
		self.assertEqual(invoice.name, "SINV-NEW")

	def test_no_payment_gate_allows_after_invoice_generation(self):
		session = make_session(payment_gate_mode="No Payment Gate", current_draft_invoice="SINV-001", latest_invoice="SINV-001")
		invoice = make_invoice(docstatus=0)

		with billing_core_context(session, invoice):
			status = billing_core.get_payment_gate_status(session)

		self.assertTrue(status["can_proceed"])

	def test_partial_payment_gate_requires_paid_amount_across_session(self):
		session = make_session(payment_gate_mode="Partial Payment Gate", latest_invoice="SINV-001", total_paid=0)
		invoice = make_invoice(docstatus=1, outstanding_amount=100)

		with billing_core_context(session, invoice, paid_amount=0):
			blocked = billing_core.get_payment_gate_status(session)
		with billing_core_context(session, invoice, paid_amount=25):
			allowed = billing_core.get_payment_gate_status(session)

		self.assertFalse(blocked["can_proceed"])
		self.assertTrue(allowed["can_proceed"])

	def test_full_payment_gate_requires_zero_session_outstanding(self):
		session = make_session(payment_gate_mode="Full Payment Gate", latest_invoice="SINV-001")
		invoice = make_invoice(docstatus=1, outstanding_amount=100)

		with billing_core_context(session, invoice, paid_amount=0):
			blocked = billing_core.get_payment_gate_status(session)
		invoice.outstanding_amount = 0
		with billing_core_context(session, invoice, paid_amount=100):
			allowed = billing_core.get_payment_gate_status(session)

		self.assertFalse(blocked["can_proceed"])
		self.assertTrue(allowed["can_proceed"])

	def test_modal_summary_returns_session_payment_gate(self):
		summary = {"name": "VBS-001", "payment_gate": {"can_proceed": True}, "invoices": []}
		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal, "get_billing_source_config", return_value=billing_modal.BILLING_SOURCE_CONFIGS["Veterinary Consultation"]),
			patch.object(billing_modal.frappe, "get_doc", return_value=frappe._dict(doctype="Veterinary Consultation", name="VCON-001", linked_invoice=None)),
			patch.object(billing_modal, "assert_can_read_source"),
			patch.object(billing_modal, "get_billing_session_summary_for_source", return_value=summary),
			patch.object(billing_modal, "get_payment_modes", return_value=[]),
		):
			state = billing_modal.get_billing_modal_state("Veterinary Consultation", "VCON-001")

		self.assertEqual(state["billing_session"], summary)
		self.assertTrue(state["payment_gate"]["can_proceed"])



	def test_global_billing_sources_are_modal_session_supported(self):
		for doctype in [
			"Veterinary Consultation",
			"Veterinary Lab Order",
			"Veterinary Vaccination Record",
			"Veterinary Hospitalisation",
			"Veterinary Patient",
			"Pet Grooming Session",
			"Pet Boarding Booking",
		]:
			self.assertTrue(billing_modal.source_supports_billing_session(doctype), doctype)

	def test_consultation_invoice_api_uses_billing_core(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", service_branch="Main", status="Draft")
		doc.save = Mock()
		settings = billing.ConsultationBillingSettings(True, "CONS-ITEM", False, False, False, True)
		with (
			patch.object(billing, "require_internal_user"),
			patch.object(billing, "can_access_consultation"),
			patch.object(billing, "get_consultation_billing_settings", return_value=settings),
			patch.object(billing, "validate_consultation_invoice_request"),
			patch.object(billing, "use_billing_core_for_source", return_value=True),
			patch.object(billing.frappe, "get_doc", side_effect=lambda doctype, name=None: doc if doctype == "Veterinary Consultation" else make_invoice(name or "SINV-001")),
			patch.object(billing.frappe.db, "get_value", return_value="Draft"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001", "created": True}) as sync,
		):
			result = billing.create_consultation_invoice("VCON-001")

		sync.assert_called_once_with("Veterinary Consultation", "VCON-001")
		self.assertEqual(result["billing_session"], "VBS-001")

	def test_lab_order_invoice_api_uses_billing_core(self):
		order = frappe._dict(doctype="Veterinary Lab Order", name="VLAB-001", linked_invoice=None, primary_owner="CUST-001", service_branch="Main")
		with (
			patch.object(lab, "require_internal_user"),
			patch.object(lab, "can_access_lab_order"),
			patch.object(lab, "get_current_user", return_value="vet@example.com"),
			patch.object(lab, "use_billing_core_for_lab_order", return_value=True),
			patch.object(lab, "is_persisted_lab_order_for_billing_core", return_value=True),
			patch.object(lab.frappe, "get_doc", return_value=order),
			patch.object(lab.frappe.db, "set_value") as set_value,
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001", "created": True}) as sync,
		):
			result = lab.create_lab_order_invoice("VLAB-001")

		sync.assert_called_once_with(lab.LAB_ORDER_DOCTYPE, "VLAB-001")
		set_value.assert_called_once()
		self.assertEqual(result["billing_session"], "VBS-001")

	def test_vaccination_invoice_api_uses_billing_core(self):
		doc = frappe._dict(doctype="Veterinary Vaccination Record", name="VVAC-001", status="Draft", linked_invoice=None)
		doc.save = Mock()
		with (
			patch.object(vaccination, "require_internal_user"),
			patch.object(vaccination.frappe, "get_doc", return_value=doc),
			patch.object(vaccination, "use_billing_core_for_vaccination", return_value=True),
			patch.object(vaccination, "get_vaccination_workflow_status", return_value="Awaiting Payment"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001"}) as sync,
		):
			result = vaccination.create_or_update_vaccination_invoice("VVAC-001")

		sync.assert_called_once_with(vaccination.VACCINATION_RECORD_DOCTYPE, "VVAC-001")
		self.assertEqual(result["billing_session"], "VBS-001")
		self.assertEqual(doc.linked_invoice, "SINV-001")

	def test_registration_invoice_uses_billing_core(self):
		doc = frappe._dict(doctype="Veterinary Patient", name="PAT-001")
		rule = registration_billing.RegistrationBillingRule(True, "Main", "REG-ITEM", 100, True, True)
		with (
			patch.object(registration_billing, "use_billing_core_for_registration", return_value=True),
			patch.object(registration_billing.frappe, "get_doc", return_value=make_invoice("SINV-001")),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "session": "VBS-001"}) as sync,
		):
			invoice = registration_billing.create_registration_invoice(doc, rule)

		sync.assert_called_once_with("Veterinary Patient", "PAT-001")
		self.assertEqual(invoice.name, "SINV-001")

	def test_grooming_invoice_uses_billing_core(self):
		doc = frappe._dict(doctype="Pet Grooming Session", name="PGS-001", status="Draft", grooming_service="Bath")
		with (
			patch.object(grooming, "is_grooming_billing_enabled", return_value=True),
			patch.object(grooming, "use_billing_core_for_grooming", return_value=True),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "created": True, "session": "VBS-001"}) as sync,
		):
			invoice, created = grooming.create_grooming_invoice(doc)

		sync.assert_called_once_with(grooming.GROOMING_SESSION_DOCTYPE, "PGS-001")
		self.assertEqual(invoice, "SINV-001")
		self.assertTrue(created)

	def test_boarding_invoice_uses_billing_core(self):
		doc = frappe._dict(doctype="Pet Boarding Booking", name="PBB-001", status="Reserved")
		doc.save = Mock()
		with (
			patch.object(boarding, "use_billing_core_for_boarding", return_value=True),
			patch.object(boarding, "sync_boarding_charge_fields"),
			patch("vetedge.services.billing_core.sync_source_to_billing_session", return_value={"invoice": "SINV-001", "created": True, "session": "VBS-001"}) as sync,
		):
			result = boarding.create_boarding_invoice_doc(doc)

		sync.assert_called_once_with(boarding.PET_BOARDING_BOOKING_DOCTYPE, "PBB-001")
		self.assertEqual(result["billing_session"], "VBS-001")
		self.assertEqual(doc.linked_invoice, "SINV-001")

	def test_adapter_dispatch_includes_grooming_and_boarding(self):
		with (
			patch.object(billing_core, "get_grooming_charge_payloads", return_value=[{"charge_key": "groom"}]) as grooming_payloads,
			patch.object(billing_core, "get_boarding_charge_payloads", return_value=[{"charge_key": "board"}]) as boarding_payloads,
		):
			self.assertEqual(billing_core.get_source_charge_payloads("Pet Grooming Session", "PGS-001")[0]["charge_key"], "groom")
			self.assertEqual(billing_core.get_source_charge_payloads("Pet Boarding Booking", "PBB-001")[0]["charge_key"], "board")

		grooming_payloads.assert_called_once_with("PGS-001", None)
		boarding_payloads.assert_called_once_with("PBB-001", None)

	def test_related_sources_join_consultation_session_context(self):
		with patch.object(billing_core.frappe.db, "get_value", side_effect=lambda doctype, name, fieldname=None, **kwargs: "VCON-001" if fieldname in {"consultation", "linked_consultation"} else None):
			self.assertEqual(billing_core.get_source_context("Veterinary Lab Order", "VLAB-001"), ("Veterinary Consultation", "VCON-001"))
			self.assertEqual(billing_core.get_source_context("Veterinary Vaccination Record", "VVAC-001"), ("Veterinary Consultation", "VCON-001"))

	def test_consultation_modal_income_account_resolution_is_schema_safe(self):
		consultation = frappe._dict(
			doctype="Veterinary Consultation",
			name="VCON-001",
			company="Company A",
			service_branch="Main",
			linked_invoice=None,
		)

		def get_field(fieldname):
			return frappe._dict(fieldname=fieldname) if fieldname == "income_account" else None

		def get_meta(doctype):
			if doctype == "Item Default":
				return frappe._dict(get_field=get_field)
			return frappe._dict(get_field=lambda fieldname: None)

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Item" and isinstance(fieldname, (list, tuple)):
				self.assertNotIn("income_account", fieldname)
				return frappe._dict(item_name="Consultation", stock_uom="Nos", standard_rate=150)
			if doctype == "Item Default":
				self.assertEqual(fieldname, "income_account")
				return None
			if doctype == "Item" and fieldname == "item_group":
				return "Services"
			if doctype == "Item Group" and fieldname in {"income_account", "default_income_account"}:
				raise AssertionError(f"Item Group.{fieldname} must not be queried when the field is absent")
			if doctype == "Company" and fieldname == "default_income_account":
				raise AssertionError("Company.default_income_account must not be queried when the field is absent")
			return None

		def sync_source(source_doctype, source_name):
			charge = billing_core.build_source_charge(
				consultation,
				"Consultation Fee",
				consultation.name,
				"CONS-ITEM",
				1,
				None,
				None,
				"CC-Main",
			)
			self.assertIsNone(charge["income_account"])
			return {"invoice": "SINV-001", "session": "VBS-001", "created": True}

		with (
			patch.object(billing_modal, "require_internal_user"),
			patch.object(billing_modal, "get_billing_source_config", return_value=billing_modal.BILLING_SOURCE_CONFIGS["Veterinary Consultation"]),
			patch.object(billing_modal.frappe, "get_doc", return_value=consultation),
			patch.object(billing_modal, "assert_can_act_on_source"),
			patch.object(billing_modal, "get_invoice_summary", return_value=None),
			patch.object(billing_modal, "get_billing_modal_state", return_value={"billing_session": {"name": "VBS-001"}}),
			patch.object(billing_modal, "is_billing_sessions_enabled", return_value=True),
			patch.object(billing_core.frappe, "get_meta", side_effect=get_meta),
			patch.object(billing_core.frappe.db, "get_value", side_effect=get_value),
			patch.object(billing_core, "get_default_company", return_value="Company A"),
			patch.object(billing_core, "sync_source_to_billing_session", side_effect=sync_source) as sync,
		):
			result = billing_modal.create_or_update_modal_invoice("Veterinary Consultation", "VCON-001")

		sync.assert_called_once_with("Veterinary Consultation", "VCON-001")
		self.assertTrue(result["created"])

	def test_build_source_charge_defaults_missing_standard_rate_to_zero(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", service_branch="Main")

		with (
			patch.object(billing_core.frappe.db, "get_value", return_value=frappe._dict(item_name="Consultation", stock_uom="Nos")),
			patch.object(billing_core, "_get_item_selling_rate", return_value=0),
			patch.object(billing_core, "_get_item_income_account", return_value=None),
		):
			charge = billing_core.build_source_charge(doc, "Consultation Fee", doc.name, "CONS-ITEM", None, None, None, "CC-Main")

		self.assertEqual(charge["qty"], 1)
		self.assertEqual(charge["rate"], 0)
		self.assertEqual(charge["amount"], 0)
		self.assertIsNone(charge["income_account"])

	def test_new_sales_invoice_totals_are_prepared_before_insert(self):
		session = make_session(charges=[])
		billing_core.add_or_update_session_charge(session, charge_payload(amount=0))
		created_invoice = make_invoice("SINV-NEW", docstatus=0, outstanding_amount=None)
		for fieldname in (
			"total",
			"net_total",
			"base_total",
			"base_net_total",
			"grand_total",
			"base_grand_total",
			"rounded_total",
			"base_rounded_total",
			"outstanding_amount",
		):
			created_invoice[fieldname] = None
		created_invoice.set_missing_values = Mock()
		created_invoice.calculate_taxes_and_totals = Mock()

		def assert_totals_prepared():
			self.assertIsNotNone(created_invoice.base_grand_total)
			self.assertIsNotNone(created_invoice.grand_total)
			self.assertEqual(len(created_invoice.get("items") or []), 1)

		created_invoice.insert.side_effect = assert_totals_prepared
		with billing_core_context(session, make_invoice("SINV-OLD"), created_invoice=created_invoice):
			result = billing_core.sync_session_charges_to_invoice(session)

		self.assertEqual(result["invoice"], "SINV-NEW")
		self.assertEqual(result["added_count"], 1)
		created_invoice.set_missing_values.assert_called()
		created_invoice.calculate_taxes_and_totals.assert_called()
		created_invoice.insert.assert_called_once()

	def test_empty_session_does_not_create_empty_invoice(self):
		session = make_session(charges=[], current_draft_invoice=None, latest_invoice=None)
		created_invoice = make_invoice("SINV-EMPTY")

		with billing_core_context(session, make_invoice("SINV-OLD"), created_invoice=created_invoice):
			invoice, created = billing_core.create_or_update_draft_invoice_for_session(session)
			result = billing_core.sync_session_charges_to_invoice(session)

		self.assertIsNone(invoice)
		self.assertFalse(created)
		self.assertIsNone(result["invoice"])
		created_invoice.insert.assert_not_called()

	def test_first_consultation_registration_required_adds_registration_charge(self):
		consultation = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", patient="PAT-001", primary_owner="CUST-001", service_branch="Main")
		patient = frappe._dict(doctype="Veterinary Patient", name="PAT-001", primary_owner="CUST-001", default_branch="Main")
		rule = frappe._dict(enabled=True, require_payment_before_first_consultation=True, registration_item="REG-ITEM", registration_fee=75, enforce_cost_center=False)
		with registration_consultation_context(consultation, patient, rule, first=True, paid=False):
			payload = billing_core.get_registration_charge_payload_for_consultation(consultation, make_session(charges=[]))

		self.assertIsNotNone(payload)
		self.assertEqual(payload["charge_key"], "Veterinary Patient:PAT-001:Registration Fee")
		self.assertEqual(payload["source_doctype"], "Veterinary Patient")
		self.assertEqual(payload["amount"], 75)

	def test_first_consultation_registration_and_consultation_create_one_draft_invoice(self):
		session = make_session(charges=[])
		billing_core.add_or_update_session_charge(session, charge_payload("consultation-fee", "CONS-ITEM", 100))
		billing_core.add_or_update_session_charge(session, {**charge_payload("Veterinary Patient:PAT-001:Registration Fee", "REG-ITEM", 75), "source_doctype": "Veterinary Patient", "source_name": "PAT-001"})
		created_invoice = make_invoice("SINV-NEW", docstatus=0, items=[])

		with billing_core_context(session, make_invoice("SINV-OLD"), created_invoice=created_invoice):
			result = billing_core.sync_session_charges_to_invoice(session)

		self.assertEqual(result["invoice"], "SINV-NEW")
		self.assertEqual(result["added_count"], 2)
		self.assertEqual(len(created_invoice.get("items") or []), 2)

	def test_rerun_consultation_registration_sync_does_not_duplicate_registration_charge(self):
		consultation = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", patient="PAT-001", primary_owner="CUST-001", service_branch="Main")
		patient = frappe._dict(doctype="Veterinary Patient", name="PAT-001", primary_owner="CUST-001", default_branch="Main")
		rule = frappe._dict(enabled=True, require_payment_before_first_consultation=True, registration_item="REG-ITEM", registration_fee=75, enforce_cost_center=False)
		session = make_session(charges=[])
		billing_core.add_or_update_session_charge(session, {**charge_payload("Veterinary Patient:PAT-001:Registration Fee", "REG-ITEM", 75), "source_doctype": "Veterinary Patient", "source_name": "PAT-001"})

		with registration_consultation_context(consultation, patient, rule, first=True, paid=False):
			payload = billing_core.get_registration_charge_payload_for_consultation(consultation, session)

		self.assertIsNone(payload)
		self.assertEqual(len(session.charges), 1)

	def test_paid_registration_is_not_added_to_consultation_session(self):
		consultation = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", patient="PAT-001", primary_owner="CUST-001", service_branch="Main")
		patient = frappe._dict(doctype="Veterinary Patient", name="PAT-001", primary_owner="CUST-001", default_branch="Main")
		rule = frappe._dict(enabled=True, require_payment_before_first_consultation=True, registration_item="REG-ITEM", registration_fee=75, enforce_cost_center=False)
		with registration_consultation_context(consultation, patient, rule, first=True, paid=True):
			self.assertIsNone(billing_core.get_registration_charge_payload_for_consultation(consultation, make_session(charges=[])))

	def test_registration_not_required_before_first_consultation_is_not_added(self):
		consultation = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", patient="PAT-001", primary_owner="CUST-001", service_branch="Main")
		patient = frappe._dict(doctype="Veterinary Patient", name="PAT-001", primary_owner="CUST-001", default_branch="Main")
		rule = frappe._dict(enabled=True, require_payment_before_first_consultation=False, registration_item="REG-ITEM", registration_fee=75, enforce_cost_center=False)
		with registration_consultation_context(consultation, patient, rule, first=True, paid=False):
			self.assertIsNone(billing_core.get_registration_charge_payload_for_consultation(consultation, make_session(charges=[])))

	def test_registration_is_not_added_when_consultation_is_not_first(self):
		consultation = frappe._dict(doctype="Veterinary Consultation", name="VCON-002", patient="PAT-001", primary_owner="CUST-001", service_branch="Main")
		patient = frappe._dict(doctype="Veterinary Patient", name="PAT-001", primary_owner="CUST-001", default_branch="Main")
		rule = frappe._dict(enabled=True, require_payment_before_first_consultation=True, registration_item="REG-ITEM", registration_fee=75, enforce_cost_center=False)
		with registration_consultation_context(consultation, patient, rule, first=False, paid=False):
			self.assertIsNone(billing_core.get_registration_charge_payload_for_consultation(consultation, make_session(charges=[])))

	def test_branch_price_list_item_price_is_used_for_source_charge(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", primary_owner="CUST-001", service_branch="Main")

		with price_list_context(branch_price_list="Main Branch Services", item_prices={"Main Branch Services": 450}):
			charge = billing_core.build_source_charge(doc, "Consultation Fee", doc.name, "Vet Treatment", 1, "Nos", None, "CC-Main")

		self.assertEqual(charge["rate"], 450)
		self.assertEqual(charge["amount"], 450)
		self.assertEqual(charge["branch"], "Main")

	def test_default_vetedge_price_list_is_used_when_branch_blank(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", service_branch="Main")

		with price_list_context(vetedge_price_list="VetEdge Default", item_prices={"VetEdge Default": 225}):
			charge = billing_core.build_source_charge(doc, "Consultation Fee", doc.name, "CONS-ITEM", 1, "Nos", None, "CC-Main")

		self.assertEqual(charge["rate"], 225)

	def test_selling_settings_price_list_is_used_when_vetedge_default_blank(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", service_branch="Main")

		with price_list_context(selling_settings_price_list="ERP Selling", item_prices={"ERP Selling": 180}):
			charge = billing_core.build_source_charge(doc, "Consultation Fee", doc.name, "CONS-ITEM", 1, "Nos", None, "CC-Main")

		self.assertEqual(charge["rate"], 180)

	def test_standard_rate_is_used_when_no_item_price_exists(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", service_branch="Main")

		with price_list_context(item_standard_rate=95, item_prices={}):
			charge = billing_core.build_source_charge(doc, "Consultation Fee", doc.name, "CONS-ITEM", 1, "Nos", None, "CC-Main")

		self.assertEqual(charge["rate"], 95)

	def test_zero_rate_returned_when_no_item_price_or_standard_rate_exists(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", service_branch="Main")

		with price_list_context(item_standard_rate=0, item_prices={}):
			charge = billing_core.build_source_charge(doc, "Consultation Fee", doc.name, "CONS-ITEM", 1, "Nos", None, "CC-Main")

		self.assertEqual(charge["rate"], 0)
		self.assertEqual(charge["amount"], 0)

	def test_explicit_source_rate_wins_over_price_list(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", service_branch="Main")

		with price_list_context(branch_price_list="Main Branch Services", item_prices={"Main Branch Services": 450}):
			charge = billing_core.build_source_charge(doc, "Treatment", "ROW-1", "CONS-ITEM", 2, "Nos", 125, "CC-Main")

		self.assertEqual(charge["rate"], 125)
		self.assertEqual(charge["amount"], 250)

	def test_item_price_optional_fields_are_schema_safe(self):
		doc = frappe._dict(doctype="Veterinary Consultation", name="VCON-001", company="Company A", service_branch="Main")

		with price_list_context(branch_price_list="Main Branch Services", item_prices={"Main Branch Services": 320}, optional_item_price_fields=False) as ctx:
			charge = billing_core.build_source_charge(doc, "Consultation Fee", doc.name, "CONS-ITEM", 1, "Nos", None, "CC-Main")

		self.assertEqual(charge["rate"], 320)
		self.assertNotIn("selling", ctx.item_price_filters)
		self.assertNotIn("uom", ctx.item_price_fields)
		self.assertNotIn("valid_from", ctx.item_price_fields)
		self.assertNotIn("valid_upto", ctx.item_price_fields)

	def test_invoice_hook_skips_refresh_during_billing_core_sync(self):
		previous = getattr(frappe.flags, "vetedge_billing_core_syncing", False)
		frappe.flags.vetedge_billing_core_syncing = True
		try:
			with (
				patch.object(billing_core, "is_billing_sessions_enabled", return_value=True),
				patch.object(billing_core, "get_sessions_for_invoice") as get_sessions,
			):
				billing_core.update_billing_sessions_from_invoice(frappe._dict(name="SINV-001"))
			get_sessions.assert_not_called()
		finally:
			frappe.flags.vetedge_billing_core_syncing = previous

	def test_billing_core_does_not_introduce_ignore_permissions(self):
		from pathlib import Path

		source = Path(billing_core.__file__).read_text()
		self.assertNotIn("ignore_permissions=True", source)


class price_list_context:
	def __init__(
		self,
		branch_price_list=None,
		vetedge_price_list=None,
		selling_settings_price_list=None,
		item_prices=None,
		item_standard_rate=0,
		optional_item_price_fields=True,
	):
		self.branch_price_list = branch_price_list
		self.vetedge_price_list = vetedge_price_list
		self.selling_settings_price_list = selling_settings_price_list
		self.item_prices = item_prices or {}
		self.item_standard_rate = item_standard_rate
		self.optional_item_price_fields = optional_item_price_fields
		self.patches = []
		self.item_price_filters = {}
		self.item_price_fields = []

	def __enter__(self):
		def exists(doctype, name=None):
			if doctype == "DocType":
				return name in {"Branch", "Veterinary Settings", "Selling Settings", "Item Price", "Item Default", "Item Group", "Company"}
			if doctype == "Price List":
				return name == "Standard Selling"
			return True

		def get_field(fieldname):
			base_fields = {"vetedge_price_list", "default_selling_price_list", "selling_price_list", "income_account"}
			item_price_fields = {"selling", "uom", "valid_from", "valid_upto"} if self.optional_item_price_fields else set()
			return frappe._dict(fieldname=fieldname) if fieldname in base_fields or fieldname in item_price_fields else None

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Item" and isinstance(fieldname, (list, tuple)):
				self_fieldnames = set(fieldname)
				if "income_account" in self_fieldnames:
					raise AssertionError("Item.income_account must not be queried")
				return frappe._dict(item_name=name, stock_uom="Nos", standard_rate=self.item_standard_rate)
			if doctype == "Item" and fieldname == "standard_rate":
				return self.item_standard_rate
			if doctype == "Item" and fieldname == "item_group":
				return "Services"
			if doctype == "Branch":
				self.assert_branch_field_safe(fieldname)
				return self.branch_price_list
			if doctype == "Item Default":
				return None
			return None

		def get_single_value(doctype, fieldname):
			if doctype == "Veterinary Settings" and fieldname == "default_selling_price_list":
				return self.vetedge_price_list
			if doctype == "Selling Settings" and fieldname == "selling_price_list":
				return self.selling_settings_price_list
			return None

		def get_all(doctype, filters=None, fields=None, order_by=None, limit=None):
			if doctype != "Item Price":
				return []
			self.item_price_filters = dict(filters or {})
			self.item_price_fields = list(fields or [])
			price_list = self.item_price_filters.get("price_list")
			rate = self.item_prices.get(price_list)
			if rate is None:
				return []
			row = frappe._dict(name="IP-001", price_list_rate=rate)
			if "uom" in self.item_price_fields:
				row.uom = "Nos"
			if "valid_from" in self.item_price_fields:
				row.valid_from = "2026-01-01"
			if "valid_upto" in self.item_price_fields:
				row.valid_upto = None
			return [row]

		self.patches = [
			patch.object(billing_core.frappe.db, "exists", side_effect=exists),
			patch.object(billing_core.frappe.db, "get_value", side_effect=get_value),
			patch.object(billing_core.frappe.db, "get_single_value", side_effect=get_single_value),
			patch.object(billing_core.frappe, "get_meta", return_value=frappe._dict(get_field=get_field)),
			patch.object(billing_core.frappe, "get_all", side_effect=get_all),
			patch.object(billing_core, "_get_item_income_account", return_value=None),
		]
		for patcher in self.patches:
			patcher.start()
		return self

	def assert_branch_field_safe(self, fieldname):
		if fieldname not in {"vetedge_price_list", "selling_price_list"}:
			raise AssertionError(f"Unexpected Branch price list field query: {fieldname}")

	def __exit__(self, exc_type, exc, tb):
		for patcher in reversed(self.patches):
			patcher.stop()
		return False


class registration_consultation_context:
	def __init__(self, consultation, patient, rule, first=True, paid=False):
		self.consultation = consultation
		self.patient = patient
		self.rule = rule
		self.first = first
		self.paid = paid
		self.patches = []

	def __enter__(self):
		def get_doc(doctype, name=None):
			if doctype == "Veterinary Patient":
				return self.patient
			if doctype == "Veterinary Consultation":
				return self.consultation
			return frappe._dict(doctype=doctype, name=name)

		self.patches = [
			patch.object(billing_core.frappe, "get_doc", side_effect=get_doc),
			patch.object(billing_core, "get_billing_cost_center", return_value="CC-Main"),
			patch.object(billing_core, "_get_item_income_account", return_value=None),
			patch.object(billing_core, "is_patient_registration_fee_paid", return_value=self.paid),
			patch("vetedge.services.registration_billing.get_registration_rule", return_value=self.rule),
			patch("vetedge.services.registration_billing.is_first_consultation_for_patient", return_value=self.first),
			patch.object(
				billing_core.frappe.db,
				"get_value",
				return_value=frappe._dict(item_name="Registration", stock_uom="Nos", standard_rate=0),
			),
		]
		for patcher in self.patches:
			patcher.start()
		return self

	def __exit__(self, exc_type, exc, tb):
		for patcher in reversed(self.patches):
			patcher.stop()
		return False


class billing_core_context:
	def __init__(self, session, linked_invoice, created_invoice=None, paid_amount=0):
		self.session = session
		self.linked_invoice = linked_invoice
		self.created_invoice = created_invoice or make_invoice("SINV-NEW")
		self.paid_amount = paid_amount
		self.patches = []

	def __enter__(self):
		def exists(doctype, name=None):
			if doctype in {"DocType", "Veterinary Settings"}:
				return True
			if doctype == "Sales Invoice":
				return bool(name)
			return True

		def get_doc(doctype, name=None):
			if isinstance(doctype, dict):
				self.created_invoice.update(doctype)
				return self.created_invoice
			if doctype == billing_core.BILLING_SESSION_DOCTYPE:
				return self.session
			if doctype == "Sales Invoice":
				if name == self.linked_invoice.name:
					return self.linked_invoice
				return self.created_invoice
			return frappe._dict(name=name)

		def get_value(doctype, name, fieldname=None, **kwargs):
			if doctype == "Sales Invoice" and fieldname == "docstatus":
				if name == self.linked_invoice.name:
					return self.linked_invoice.docstatus
				return self.created_invoice.docstatus
			return None

		frappe_stub = SimpleNamespace(
			db=SimpleNamespace(exists=exists, get_value=get_value),
			get_doc=get_doc,
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: False),
			get_single=lambda doctype: frappe._dict(enable_billing_sessions=1),
			get_all=Mock(return_value=[]),
			_dict=frappe._dict,
			ValidationError=frappe.ValidationError,
			throw=Mock(side_effect=frappe.ValidationError),
		)
		self.patches = [
			patch.object(billing_core, "frappe", frappe_stub),
			patch.object(billing_core, "get_default_company", return_value="Company A"),
			patch.object(billing_core, "get_billing_cost_center", return_value="CC-Main"),
			patch.object(
				billing_core,
				"get_invoice_payment_state",
				side_effect=lambda invoice: {
					"invoice": invoice,
					"paid_amount": self.paid_amount,
					"outstanding_amount": self.linked_invoice.outstanding_amount if invoice == self.linked_invoice.name else self.created_invoice.outstanding_amount,
					"has_payment": self.paid_amount > 0,
					"is_fully_paid": (self.linked_invoice.outstanding_amount if invoice == self.linked_invoice.name else self.created_invoice.outstanding_amount) <= 0,
				},
			),
		]
		for patcher in self.patches:
			patcher.start()
		return self

	def __exit__(self, exc_type, exc, tb):
		for patcher in reversed(self.patches):
			patcher.stop()
		return False
