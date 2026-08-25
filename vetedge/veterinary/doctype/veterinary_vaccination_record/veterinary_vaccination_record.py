from __future__ import annotations

import frappe
from frappe.model.document import Document

from vetedge.services import vaccination as vaccination_service
from vetedge.services.vaccination_payment_workflow import (
	enforce_vaccination_payment_before_administration,
)

# The service endpoint resolves this function from the vaccination module after
# loading the Vaccination Record controller via frappe.get_doc(). Keep every
# administration path (API, native form and EdgeSuite) on the same hardened
# billing/payment gate without maintaining a second clinical implementation.
vaccination_service.enforce_vaccination_payment_before_administration = (
	enforce_vaccination_payment_before_administration
)
validate_vaccination_record = vaccination_service.validate_vaccination_record


def sync_next_vaccination_appointment_from_record(*args, **kwargs):
	from vetedge.services.appointment_flow import sync_next_vaccination_appointment_from_record as _sync_next_vaccination_appointment_from_record
	return _sync_next_vaccination_appointment_from_record(*args, **kwargs)


def _session_has_vaccination_charge(session, record_name: str) -> bool:
	plan_prefix = f"consultation-plan::Vaccination::{record_name}::"
	direct_prefix = f"Veterinary Vaccination Record:{record_name}:Vaccination:"
	return any(
		str(row.get("charge_key") or "").startswith((plan_prefix, direct_prefix))
		and row.get("billing_status") not in {"Cancelled", "Skipped"}
		for row in session.get("charges") or []
	)


def _sync_existing_vaccination_billing_session(doc) -> None:
	"""Reconcile exactly one active billing cycle after Vaccination plan projection.

	Consultation-plan projection is deliberately side-effect-safe because Billing
	Core also invokes it while rebuilding consultation payloads. A source document
	update therefore performs the one explicit Consultation Billing Session sync
	here. Standalone Vaccinations retain their direct-source fallback.
	"""
	flags = getattr(frappe, "flags", None)
	if getattr(flags, "vetedge_billing_core_syncing", False):
		return

	if doc.get("linked_consultation"):
		from vetedge.services.consultation_billing_plan import _sync_active_consultation_billing_session

		consultation = frappe.get_doc("Veterinary Consultation", doc.linked_consultation)
		_sync_active_consultation_billing_session(consultation)
		return

	from vetedge.services.billing_core import (
		is_billing_sessions_enabled,
		resolve_billing_session,
		sync_session_charges_to_invoice,
		sync_single_source_to_billing_session,
	)

	if not is_billing_sessions_enabled():
		return
	try:
		session = resolve_billing_session(doc.doctype, doc.name)
	except Exception:
		return
	if not session:
		return

	if not _session_has_vaccination_charge(session, doc.name):
		sync_single_source_to_billing_session(session, doc.doctype, doc.name)
		session = frappe.get_doc(session.doctype, session.name)

	# If standalone billing already has an active Draft, add/update the Vaccination there.
	# If the previous invoice is submitted, Billing Core safely creates a new
	# draft for the new service instead of mutating that submitted invoice.
	sync_session_charges_to_invoice(session.name)


class VeterinaryVaccinationRecord(Document):
	def validate(self) -> None:
		validate_vaccination_record(self)
		from vetedge.services.appointment_vaccination_bridge import validate_vaccination_record_appointment_link

		validate_vaccination_record_appointment_link(self)
		if not self.get("billing_item"):
			frappe.throw(
				"The selected Vaccine has no ERPNext billing Item. Configure Default Item on the Veterinary Vaccine master before using it.",
				frappe.ValidationError,
			)
		from vetedge.services.consultation_related_records import validate_consultation_vaccination_duplicate

		validate_consultation_vaccination_duplicate(self)

	def after_insert(self) -> None:
		from vetedge.services.consultation_billing_plan import sync_vaccination_to_consultation_plan

		sync_vaccination_to_consultation_plan(self)
		_sync_existing_vaccination_billing_session(self)
		sync_next_vaccination_appointment_from_record(self)

	def on_update(self) -> None:
		from vetedge.services.consultation_billing_plan import sync_vaccination_to_consultation_plan

		sync_vaccination_to_consultation_plan(self)
		_sync_existing_vaccination_billing_session(self)
		sync_next_vaccination_appointment_from_record(self)
