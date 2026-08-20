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


class VeterinaryVaccinationRecord(Document):
	def validate(self) -> None:
		validate_vaccination_record(self)
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
		sync_next_vaccination_appointment_from_record(self)

	def on_update(self) -> None:
		from vetedge.services.consultation_billing_plan import sync_vaccination_to_consultation_plan

		sync_vaccination_to_consultation_plan(self)
		sync_next_vaccination_appointment_from_record(self)
