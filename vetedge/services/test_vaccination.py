from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch


def _install_stub_modules() -> None:
	if "frappe" in sys.modules and hasattr(sys.modules["frappe"], "db") and hasattr(sys.modules["frappe"].db, "sql"):
		return

	if "frappe" not in sys.modules:
		frappe = ModuleType("frappe")
		frappe.ValidationError = Exception
		frappe.PermissionError = Exception
		frappe.throw = Mock(side_effect=Exception("blocked"))
		frappe.whitelist = lambda *args, **kwargs: (lambda fn: fn)
		frappe.validate_and_sanitize_search_inputs = lambda fn: fn
		frappe.has_permission = lambda *args, **kwargs: True
		frappe.get_roles = lambda user=None: []
		frappe._dict = dict
		frappe.parse_json = lambda value: value
		frappe.db = SimpleNamespace(get_value=Mock(), exists=Mock(return_value=False))
		frappe.session = SimpleNamespace(user="test@example.com")
		sys.modules["frappe"] = frappe

	if "frappe.permissions" not in sys.modules:
		sys.modules["frappe.permissions"] = ModuleType("frappe.permissions")

	if "frappe.utils" not in sys.modules:
		utils = ModuleType("frappe.utils")
		utils.add_days = lambda value, days: date.fromisoformat(str(value).split(" ")[0]).fromordinal(date.fromisoformat(str(value).split(" ")[0]).toordinal() + days)
		utils.cint = lambda value=0: int(value or 0)
		utils.flt = lambda value=0: float(value or 0)
		utils.get_datetime = lambda value=None: datetime.fromisoformat(str(value).replace(" ", "T")) if value else datetime.now()
		utils.getdate = lambda value=None: date.fromisoformat(str(value).split(" ")[0]) if value else date.today()
		utils.nowdate = lambda: date.today().isoformat()
		utils.now_datetime = datetime.now
		sys.modules["frappe.utils"] = utils

	stubs = {
		"vetedge.services.appointment_flow": {
			"emit_appointment_event": lambda *args, **kwargs: None,
		},
		"vetedge.services.billing": {
			"PAID_STATUS": "Paid",
			"build_invoice_item": lambda item_code, qty, uom, rate, cost_center: {
				"item_code": item_code,
				"qty": qty,
				"uom": uom,
				"rate": rate,
				"amount": qty,
				"cost_center": cost_center,
			},
			"create_consultation_invoice": lambda consultation, update_status=1: {"invoice": "SINV-CONS-001"},
			"get_consultation_billing_settings": lambda: SimpleNamespace(enabled=True, requires_payment_before_treatment=False),
			"get_invoice_payment_status": lambda invoice: "Unpaid",
			"validate_sales_item": lambda *args, **kwargs: None,
		},
		"vetedge.services.expiry_control": {
			"allocate_item_batches": lambda *args, **kwargs: [],
			"summarize_allocations": lambda allocations: "",
			"validate_stock_item_expiry_configuration": lambda *args, **kwargs: None,
		},
		"vetedge.services.feature_flags": {"is_enabled": lambda feature: True},
		"vetedge.services.notifications": {"emit_notification_event": lambda *args, **kwargs: None},
		"vetedge.services.portal_access": {"require_internal_user": lambda: None},
		"vetedge.services.registration_billing": {
			"get_billing_cost_center": lambda *args, **kwargs: "Main - CC",
			"get_default_company": lambda: "Default Company",
		},
		"vetedge.services.stock": {
			"build_stock_entry_rows": lambda *args, **kwargs: [],
			"get_branch_dispensary_warehouse": lambda *args, **kwargs: "Stores - WH",
			"get_item_stock_profile": lambda *args, **kwargs: SimpleNamespace(is_stock_item=False, has_batch_no=False, stock_uom="Nos"),
			"validate_stock_availability": lambda *args, **kwargs: None,
		},
		"vetedge.services.permissions": {
			"ELEVATED_ROLES": {"System Manager", "VetEdge Administrator"},
			"can_dispense": lambda *args, **kwargs: True,
			"DOCTOR_ROLES": {"VetEdge Doctor", "System Manager", "VetEdge Administrator"},
			"FRONT_DESK_ROLES": {"VetEdge Front Desk", "System Manager", "VetEdge Administrator"},
			"ROLE_VETERINARY_NURSE": "Veterinary Nurse",
			"can_access_branch_data": lambda *args, **kwargs: True,
			"can_access_consultation": lambda *args, **kwargs: True,
			"get_assigned_branches": lambda *args, **kwargs: ["Main Branch"],
			"get_current_user": lambda: "doctor@example.com",
			"is_internal_staff_user": lambda user=None: True,
			"user_has_any_role": lambda user, roles: False,
		},
	}
	for name, attrs in stubs.items():
		if name in sys.modules:
			continue
		module = ModuleType(name)
		for attr_name, value in attrs.items():
			setattr(module, attr_name, value)
		sys.modules[name] = module


_install_stub_modules()

from vetedge.services import vaccination


class VaccinationPermissionTests(TestCase):
	def test_doctor_can_administer_vaccine(self):
		with patch.object(vaccination, "is_internal_staff_user", return_value=True), patch.object(
			vaccination,
			"user_has_any_role",
			side_effect=lambda user, roles: "VetEdge Doctor" in roles,
		), patch.object(vaccination, "require_vaccination_branch_access") as branch_check:
			self.assertTrue(vaccination.can_administer_vaccine("doctor@example.com", SimpleNamespace(service_branch="Main")))
			branch_check.assert_called_once()

	def test_front_desk_cannot_administer_vaccine(self):
		with patch.object(vaccination, "is_internal_staff_user", return_value=True), patch.object(
			vaccination,
			"user_has_any_role",
			return_value=False,
		):
			self.assertFalse(vaccination.can_administer_vaccine("frontdesk@example.com", SimpleNamespace(service_branch="Main")))

	def test_administered_record_is_read_only_for_non_admin(self):
		doc = SimpleNamespace(
			doctype="Veterinary Vaccination Record",
			name="VVAC-1",
			status="Administered",
			linked_invoice=None,
			stock_entry_reference=None,
			meta=SimpleNamespace(
				fields=[
					SimpleNamespace(fieldname="status"),
					SimpleNamespace(fieldname="notes"),
					SimpleNamespace(fieldname="linked_invoice"),
					SimpleNamespace(fieldname="stock_entry_reference"),
				]
			),
			get=lambda fieldname: getattr(doc, fieldname),
		)
		doc.notes = "changed"
		previous = SimpleNamespace(status="Administered", notes="old", linked_invoice=None, stock_entry_reference=None, get=lambda fieldname: getattr(previous, fieldname))
		frappe_stub = SimpleNamespace(PermissionError=Exception, throw=Mock(side_effect=Exception("blocked")))

		with patch.object(vaccination, "frappe", frappe_stub), patch.object(vaccination, "user_has_any_role", return_value=False):
			with self.assertRaises(Exception):
				vaccination.validate_administered_record_edit(doc, previous)


class VaccinationContextTests(TestCase):
	def test_owner_resolves_from_patient_primary_owner(self):
		doc = SimpleNamespace(
			patient="PAT-001",
			vaccine="Rabies",
			linked_consultation=None,
			primary_owner=None,
			service_branch=None,
			company=None,
			status="Draft",
		)
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			throw=Mock(side_effect=Exception("blocked")),
			db=SimpleNamespace(
				get_value=Mock(return_value=SimpleNamespace(primary_owner="CUST-001", default_branch="Main Branch", species="Canine"))
			),
		)
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(vaccination, "get_default_company", return_value="VetEdge Co"):
			vaccination.resolve_record_context(doc)

		self.assertEqual(doc.primary_owner, "CUST-001")
		self.assertEqual(doc.service_branch, "Main Branch")
		self.assertEqual(doc.company, "VetEdge Co")


class VaccinationDueDateTests(TestCase):
	def test_next_due_date_uses_default_next_due_days(self):
		doc = SimpleNamespace(vaccine="Rabies", administered_on="2026-04-30", next_due_date=None)
		with patch.object(
			vaccination,
			"get_vaccine_defaults",
			return_value=vaccination.VaccineDefaults(default_next_due_days=365),
		):
			vaccination.calculate_next_due_date(doc)

		self.assertEqual(str(doc.next_due_date), "2027-04-30")

	def test_next_due_date_falls_back_to_default_validity_days(self):
		doc = SimpleNamespace(vaccine="Rabies", administered_on="2026-04-30", next_due_date=None)
		with patch.object(
			vaccination,
			"get_vaccine_defaults",
			return_value=vaccination.VaccineDefaults(default_next_due_days=0, default_validity_days=180),
		):
			vaccination.calculate_next_due_date(doc)

		self.assertEqual(str(doc.next_due_date), "2026-10-27")

	def test_manual_next_due_date_is_preserved(self):
		doc = SimpleNamespace(vaccine="Rabies", administered_on="2026-04-30", next_due_date="2026-12-01")
		with patch.object(vaccination, "get_vaccine_defaults") as defaults:
			vaccination.calculate_next_due_date(doc)

		defaults.assert_not_called()
		self.assertEqual(doc.next_due_date, "2026-12-01")


class VaccinationBatchTests(TestCase):
	def test_expired_batch_is_rejected(self):
		doc = SimpleNamespace(vaccine="Rabies", batch_no="BATCH-001", expiry_date=None, administered_on="2026-04-30")
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			throw=Mock(side_effect=Exception("expired")),
			db=SimpleNamespace(get_value=Mock(return_value=SimpleNamespace(item="ITEM-001", expiry_date="2026-04-01", disabled=0))),
		)
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(
			vaccination,
			"get_vaccine_defaults",
			return_value=vaccination.VaccineDefaults(default_item="ITEM-001"),
		):
			with self.assertRaises(Exception):
				vaccination.validate_stock_batch(doc)

	def test_expiry_date_is_derived_from_batch(self):
		doc = SimpleNamespace(vaccine="Rabies", batch_no="BATCH-001", expiry_date="2099-01-01", administered_on="2026-04-30")
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			throw=Mock(side_effect=Exception("blocked")),
			db=SimpleNamespace(get_value=Mock(return_value=SimpleNamespace(item="ITEM-001", expiry_date="2026-06-01", disabled=0))),
		)
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(
			vaccination,
			"get_vaccine_defaults",
			return_value=vaccination.VaccineDefaults(default_item="ITEM-001"),
		):
			vaccination.validate_stock_batch(doc)

		self.assertEqual(str(doc.expiry_date), "2026-06-01")


class VaccinationWorkflowTests(TestCase):
	def test_create_vaccination_from_consultation_creates_record_and_invoice(self):
		consultation_doc = SimpleNamespace(
			name="CONS-001",
			patient="PAT-001",
			primary_owner="CUST-001",
			service_branch="Main Branch",
			company="VetEdge Co",
		)
		record_doc = SimpleNamespace(name="VVAC-001", status="Draft", linked_invoice=None, next_due_date=None, insert=Mock(), reload=Mock())
		frappe_stub = SimpleNamespace(
			ValidationError=Exception,
			PermissionError=Exception,
			has_permission=Mock(return_value=True),
			get_doc=Mock(side_effect=[consultation_doc, record_doc]),
			parse_json=lambda value: value,
		)
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(vaccination, "require_internal_user"), patch.object(
			vaccination, "ensure_vaccination_enabled"
		), patch.object(vaccination, "can_access_consultation"), patch.object(
			vaccination, "require_vaccination_branch_access"
		), patch.object(
			vaccination,
			"create_or_update_vaccination_invoice",
			return_value={"name": "VVAC-001", "vaccination_record": "VVAC-001", "invoice": "INV-001", "status": "Awaiting Payment"},
		) as update_invoice:
			result = vaccination.create_vaccination_from_consultation(
				"CONS-001",
				values={"vaccine": "Rabies", "dose": "1 ml", "route": "Subcutaneous"},
			)

		record_doc.insert.assert_called_once()
		payload = frappe_stub.get_doc.call_args_list[1].args[0]
		self.assertEqual(payload["status"], "Draft")
		self.assertEqual(payload["primary_owner"], "CUST-001")
		self.assertEqual(result["linked_invoice"], "INV-001")
		self.assertEqual(result["status"], "Awaiting Payment")
		update_invoice.assert_called_once_with("VVAC-001")

	def test_due_vaccinations_default_to_next_30_days(self):
		frappe_stub = SimpleNamespace(get_list=Mock(return_value=[]))
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(vaccination, "getdate", return_value=date(2026, 4, 30)), patch.object(
			vaccination, "add_days", return_value=date(2026, 5, 30)
		):
			vaccination._get_due_vaccinations()

		filters = frappe_stub.get_list.call_args.kwargs["filters"]
		self.assertEqual(filters["next_due_date"], ["between", [date(2026, 4, 30), date(2026, 5, 30)]])

	def test_vaccination_uses_consultation_invoice_builder(self):
		doc = SimpleNamespace(vaccine="Rabies", service_branch="Main Branch", linked_invoice=None, linked_consultation="CONS-001", primary_owner="CUST-001", company="VetEdge Co", administered_on="2026-04-30", name="VVAC-001")
		with patch.object(vaccination, "get_vaccine_defaults", return_value=vaccination.VaccineDefaults(default_item="ITEM-001")), patch.object(
			vaccination, "create_consultation_invoice", return_value={"invoice": "SINV-CONS-001"}
		) as create_invoice, patch.object(
			vaccination, "use_billing_core_for_vaccination", return_value=False
		):
			invoice_name = vaccination.create_vaccination_invoice(doc)

		self.assertEqual(invoice_name, "SINV-CONS-001")
		create_invoice.assert_called_once_with("CONS-001", update_status=0)

	def test_consultation_vaccination_action_saves_dirty_consultation_before_creation(self):
		script_path = (
			Path(__file__).resolve().parents[1]
			/ "veterinary"
			/ "doctype"
			/ "veterinary_consultation"
			/ "veterinary_consultation.js"
		)
		script = script_path.read_text()

		self.assertIn("if (frm.is_dirty())", script)
		self.assertLess(
			script.index("await frm.save();"),
			script.index('method: "vetedge.services.vaccination.create_vaccination_from_consultation"'),
		)
		self.assertIn("create_invoice: 0", script)
		self.assertIn("frm.reload_doc();", script)

	def test_payment_required_blocks_administer_for_non_manager(self):
		doc = SimpleNamespace(status="Awaiting Payment", service_branch="Main Branch", linked_consultation="CONS-001", linked_invoice="SINV-001")
		invoice = SimpleNamespace(docstatus=1)
		frappe_stub = SimpleNamespace(get_doc=Mock(return_value=invoice), ValidationError=Exception, throw=Mock(side_effect=Exception("blocked")))
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(vaccination, "get_consultation_billing_settings", return_value=SimpleNamespace(enabled=True, requires_payment_before_treatment=True)), patch.object(
			vaccination, "user_has_any_role", return_value=False
		), patch.object(vaccination, "get_invoice_payment_status", return_value="Unpaid"):
			with self.assertRaises(Exception):
				vaccination.enforce_vaccination_payment_before_administration(doc, user="frontdesk@example.com")

	def test_manager_override_can_administer_without_payment(self):
		doc = SimpleNamespace(status="Awaiting Payment", service_branch="Main Branch", linked_consultation="CONS-001", linked_invoice="SINV-001")
		with patch.object(vaccination, "get_consultation_billing_settings", return_value=SimpleNamespace(enabled=True, requires_payment_before_treatment=True)), patch.object(
			vaccination, "user_has_any_role", return_value=True
		):
			vaccination.enforce_vaccination_payment_before_administration(doc, user="manager@example.com")

	def test_get_consultation_vaccinations_is_consultation_scoped(self):
		rows = [SimpleNamespace(name="VVAC-001", vaccine="Rabies", administered_on="2026-04-30 09:00:00", service_branch="Main Branch", administered_by="doctor@example.com", next_due_date="2027-04-30", status="Administered", linked_consultation="CONS-001", linked_invoice=None, stock_entry_reference=None, dose="1 ml", route="Subcutaneous", primary_owner="CUST-001")]
		frappe_stub = SimpleNamespace(
			has_permission=Mock(return_value=True),
			get_list=Mock(return_value=rows),
			get_all=Mock(return_value=[]),
			PermissionError=Exception,
			throw=Mock(side_effect=Exception("blocked")),
		)
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(vaccination, "require_internal_user"), patch.object(vaccination, "can_access_consultation"):
			result = vaccination.get_consultation_vaccinations("CONS-001", limit=20)
		filters = frappe_stub.get_list.call_args.kwargs["filters"]
		self.assertEqual(filters["linked_consultation"], "CONS-001")
		self.assertEqual(result[0]["vaccine"], "Rabies")

	def test_next_due_appointment_is_created(self):
		doc = SimpleNamespace(
			name="VVAC-001",
			patient="PAT-001",
			primary_owner="CUST-001",
			service_branch="Main Branch",
			administered_by="doctor@example.com",
			linked_consultation="CONS-001",
			next_due_date="2026-05-30",
			vaccine="Rabies",
		)
		appointment_doc = SimpleNamespace(name="VAPP-001", insert=Mock())
		frappe_stub = SimpleNamespace(get_all=Mock(return_value=[]), get_doc=Mock(return_value=appointment_doc))
		with patch.object(vaccination, "frappe", frappe_stub), patch.object(vaccination, "is_appointment_creation_enabled", return_value=True), patch.object(
			vaccination, "emit_appointment_event"
		) as emit_event:
			name = vaccination.create_next_due_vaccination_appointment(doc)

		self.assertEqual(name, "VAPP-001")
		appointment_doc.insert.assert_called_once_with(ignore_permissions=True)
		emit_event.assert_called_once()
