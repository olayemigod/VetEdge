from __future__ import annotations

from unittest import TestCase
from unittest.mock import Mock, patch

import frappe

from vetedge.services import billing_core
from vetedge.services import invoice_cancellation_recovery as recovery


def make_session(*, status="Active", charges=None):
	session = frappe._dict(
		name="VBS-001",
		status=status,
		current_draft_invoice=None,
		latest_invoice="SINV-CANCELLED",
		charges=charges or [],
	)
	session.append = lambda fieldname, row: session.setdefault(fieldname, []).append(frappe._dict(row)) or session[fieldname][-1]
	session.save = Mock()
	return session


def make_charge(key="service-charge", **values):
	data = {
		"source_doctype": "Veterinary Lab Order",
		"source_name": "VLAB-001",
		"source_detail_name": "CBC",
		"charge_key": key,
		"item_code": "LAB-CBC",
		"item_name": "CBC",
		"description": "CBC",
		"qty": 1,
		"rate": 5000,
		"amount": 5000,
		"invoice": "SINV-CANCELLED",
		"invoice_item_name": "ITEM-ROW-1",
		"billing_status": "Cancelled",
		"notes": None,
	}
	data.update(values)
	return frappe._dict(data)


def make_payload(key="service-charge", *, legacy_keys=None):
	return {
		"source_doctype": "Veterinary Lab Order",
		"source_name": "VLAB-001",
		"source_detail_name": "CBC",
		"charge_key": key,
		"legacy_charge_keys": legacy_keys or [],
		"item_code": "LAB-CBC",
		"item_name": "CBC",
		"description": "CBC",
		"qty": 1,
		"rate": 5000,
		"amount": 5000,
	}


class TestInvoiceCancellationRecovery(TestCase):
	def test_cancelled_invoice_reopens_still_valid_service_charge(self):
		historical = make_charge()
		session = make_session(status="Closed", charges=[historical])
		payload = make_payload()

		def add_or_update(session_arg, payload_arg):
			row = frappe._dict(payload_arg.copy())
			row.billing_status = "Pending"
			row.invoice = None
			row.invoice_item_name = None
			session_arg.charges.append(row)
			return row

		with (
			patch.object(billing_core, "ensure_session_doc", return_value=session),
			patch.object(billing_core, "get_source_charge_payloads", return_value=[payload]),
			patch.object(billing_core, "add_or_update_session_charge", side_effect=add_or_update),
			patch.object(billing_core, "refresh_billing_session_totals") as refresh,
		):
			reopened = recovery.reopen_session_charges_for_cancelled_invoice(session.name, "SINV-CANCELLED")

		self.assertEqual(reopened, 1)
		self.assertEqual(len(session.charges), 2)
		self.assertTrue(historical.charge_key.startswith("cancelled-invoice::SINV-CANCELLED::"))
		self.assertEqual(historical.invoice, "SINV-CANCELLED")
		self.assertEqual(historical.billing_status, "Cancelled")
		self.assertEqual(session.charges[1].charge_key, "service-charge")
		self.assertIsNone(session.charges[1].invoice)
		self.assertEqual(session.charges[1].billing_status, "Pending")
		self.assertEqual(session.status, "Active")
		refresh.assert_called_once_with(session)
		session.save.assert_called_once()

	def test_removed_or_cancelled_service_is_not_resurrected(self):
		historical = make_charge()
		session = make_session(charges=[historical])

		with (
			patch.object(billing_core, "ensure_session_doc", return_value=session),
			patch.object(billing_core, "get_source_charge_payloads", return_value=[]),
			patch.object(billing_core, "add_or_update_session_charge") as add_charge,
			patch.object(billing_core, "refresh_billing_session_totals") as refresh,
		):
			reopened = recovery.reopen_session_charges_for_cancelled_invoice(session.name, "SINV-CANCELLED")

		self.assertEqual(reopened, 0)
		self.assertEqual(historical.charge_key, "service-charge")
		self.assertEqual(historical.billing_status, "Cancelled")
		add_charge.assert_not_called()
		refresh.assert_not_called()
		session.save.assert_not_called()

	def test_legacy_charge_key_can_reopen_to_current_canonical_key(self):
		historical = make_charge("legacy-lab-key")
		session = make_session(charges=[historical])
		payload = make_payload("consultation-plan::Lab Order::VLAB-001::CBC", legacy_keys=["legacy-lab-key"])

		def add_or_update(session_arg, payload_arg):
			row = frappe._dict(payload_arg.copy())
			session_arg.charges.append(row)
			return row

		with (
			patch.object(billing_core, "ensure_session_doc", return_value=session),
			patch.object(billing_core, "get_source_charge_payloads", return_value=[payload]),
			patch.object(billing_core, "add_or_update_session_charge", side_effect=add_or_update),
			patch.object(billing_core, "refresh_billing_session_totals"),
		):
			reopened = recovery.reopen_session_charges_for_cancelled_invoice(session.name, "SINV-CANCELLED")

		self.assertEqual(reopened, 1)
		self.assertEqual(session.charges[1].charge_key, "consultation-plan::Lab Order::VLAB-001::CBC")
		self.assertEqual(session.charges[1].billing_status, "Pending")

	def test_recovery_is_repeat_safe(self):
		historical = make_charge()
		pending = frappe._dict(make_payload())
		pending.invoice = None
		pending.invoice_item_name = None
		pending.billing_status = "Pending"
		recovery.archive_historical_charge(historical, "SINV-CANCELLED", "service-charge")
		session = make_session(charges=[historical, pending])

		with (
			patch.object(billing_core, "ensure_session_doc", return_value=session),
			patch.object(billing_core, "get_source_charge_payloads", return_value=[make_payload()]),
			patch.object(billing_core, "add_or_update_session_charge") as add_charge,
		):
			reopened = recovery.reopen_session_charges_for_cancelled_invoice(session.name, "SINV-CANCELLED")

		self.assertEqual(reopened, 0)
		self.assertEqual(len(session.charges), 2)
		add_charge.assert_not_called()

	def test_sales_invoice_cancel_hook_clears_stale_links_then_reopens_sessions(self):
		invoice = frappe._dict(name="SINV-CANCELLED", docstatus=2)
		with (
			patch.object(billing_core, "is_billing_sessions_enabled", return_value=True),
			patch.object(billing_core, "get_sessions_for_invoice", return_value=["VBS-001", "VBS-002"]),
			patch.object(billing_core, "detach_invoice_from_vetedge_sources") as detach,
			patch.object(recovery, "reopen_session_charges_for_cancelled_invoice") as reopen,
		):
			recovery.reopen_active_service_billing_after_invoice_cancel(invoice)

		detach.assert_called_once_with("SINV-CANCELLED", reason="cancelled_invoice_rebilling")
		self.assertEqual(
			[item.args for item in reopen.call_args_list],
			[
				("VBS-001", "SINV-CANCELLED"),
				("VBS-002", "SINV-CANCELLED"),
			],
		)

	def test_non_cancelled_invoice_does_nothing(self):
		invoice = frappe._dict(name="SINV-SUBMITTED", docstatus=1)
		with patch.object(billing_core, "get_sessions_for_invoice") as sessions:
			recovery.reopen_active_service_billing_after_invoice_cancel(invoice)
		sessions.assert_not_called()

	def test_hook_is_registered_after_billing_core_reconciliation(self):
		from vetedge import hooks

		handlers = hooks.doc_events["Sales Invoice"]["on_cancel"]
		self.assertIn("vetedge.services.billing_core.update_billing_sessions_from_invoice", handlers)
		self.assertIn("vetedge.services.invoice_cancellation_recovery.reopen_active_service_billing_after_invoice_cancel", handlers)
		self.assertGreater(
			handlers.index("vetedge.services.invoice_cancellation_recovery.reopen_active_service_billing_after_invoice_cancel"),
			handlers.index("vetedge.services.billing_core.update_billing_sessions_from_invoice"),
		)
