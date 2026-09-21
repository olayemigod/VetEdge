from __future__ import annotations

import hashlib

from frappe.utils import cint

from vetedge.services import billing_core


CANCELLED_INVOICE_ARCHIVE_PREFIX = "cancelled-invoice"


def reopen_active_service_billing_after_invoice_cancel(doc, method: str | None = None) -> None:
	"""Reopen still-valid VetEdge billing charges after a Sales Invoice is cancelled.

	A cancelled accounting document remains immutable history. The historical
	Billing Session Charge remains linked to it, while a fresh Pending charge is
	created only when the underlying service payload still exists.
	"""
	if cint(doc.get("docstatus")) != 2 or not billing_core.is_billing_sessions_enabled():
		return

	invoice_name = doc.get("name")
	if not invoice_name:
		return

	session_names = billing_core.get_sessions_for_invoice(invoice_name)
	if not session_names:
		return

	# Remove stale current-source pointers before rebuilding payload truth. This
	# does not alter the cancelled Sales Invoice; Billing Session history below
	# retains the invoice evidence.
	billing_core.detach_invoice_from_vetedge_sources(
		invoice_name,
		reason="cancelled_invoice_rebilling",
	)

	for session_name in session_names:
		reopen_session_charges_for_cancelled_invoice(session_name, invoice_name)


def reopen_session_charges_for_cancelled_invoice(session_name: str, invoice_name: str) -> int:
	session = billing_core.ensure_session_doc(session_name)
	candidates = [
		row
		for row in session.get("charges") or []
		if row.get("invoice") == invoice_name and row.get("billing_status") == "Cancelled"
	]
	if not candidates:
		return 0

	payload_cache: dict[tuple[str, str], list[dict]] = {}
	reopened = 0

	for historical_charge in candidates:
		source_doctype = historical_charge.get("source_doctype")
		source_name = historical_charge.get("source_name")
		if not source_doctype or not source_name:
			continue

		cache_key = (source_doctype, source_name)
		if cache_key not in payload_cache:
			try:
				payload_cache[cache_key] = billing_core.get_source_charge_payloads(
					source_doctype,
					source_name,
					session,
				)
			except Exception:
				# Fail closed: a source that cannot prove a current billable payload
				# must not be resurrected automatically.
				payload_cache[cache_key] = []

		payload = find_matching_current_payload(historical_charge, payload_cache[cache_key])
		if not payload:
			continue

		original_key = historical_charge.get("charge_key") or billing_core.build_charge_key(payload)
		archive_historical_charge(historical_charge, invoice_name, original_key)

		current_charge = billing_core.add_or_update_session_charge(session, payload)
		current_charge.invoice = None
		current_charge.invoice_item_name = None
		current_charge.billing_status = "Pending"
		current_charge.notes = append_note(
			current_charge.get("notes"),
			f"Reopened for replacement billing after cancelled invoice {invoice_name}.",
		)
		reopened += 1

	if not reopened:
		return 0

	if session.get("current_draft_invoice") == invoice_name:
		session.current_draft_invoice = None
	if session.get("status") == "Closed":
		session.status = "Active"

	billing_core.refresh_billing_session_totals(session)
	session.save()
	return reopened


def find_matching_current_payload(historical_charge, payloads: list[dict]):
	historical_key = historical_charge.get("charge_key")
	if not historical_key:
		return None
	for payload in payloads or []:
		if historical_key in billing_core.get_payload_charge_keys(payload):
			return payload
	return None


def archive_historical_charge(historical_charge, invoice_name: str, original_key: str) -> None:
	historical_charge.charge_key = build_archived_charge_key(invoice_name, original_key)
	historical_charge.billing_status = "Cancelled"
	historical_charge.notes = append_note(
		historical_charge.get("notes"),
		f"Cancelled invoice history {invoice_name}; original charge key: {original_key}.",
	)


def build_archived_charge_key(invoice_name: str, original_key: str) -> str:
	digest = hashlib.sha256(f"{invoice_name}|{original_key}".encode()).hexdigest()[:16]
	return f"{CANCELLED_INVOICE_ARCHIVE_PREFIX}::{invoice_name}::{digest}"


def append_note(existing: str | None, note: str) -> str:
	return "; ".join(part for part in [existing, note] if part)
