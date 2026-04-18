from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.registration_billing import validate_registration_settings


class VeterinarySettings(Document):
	def validate(self) -> None:
		if not self.enable_vetedge:
			self.enable_registration_billing = 0
			self.enable_consultations = 0
			self.enable_vitals = 0
			self.require_vitals_before_completion = 0
			self.enable_appointments = 0
			self.enable_owner_portal = 0
			self.enable_guest_booking = 0
			self.enable_notifications = 0
			self.enable_treatment_billing = 0
			self.enable_dispensary_flow = 0
			self.enable_vaccination = 0
			self.enable_boarding = 0
			self.enable_demo_tools = 0
			self.enable_advanced_reports = 0

		if not self.enable_vitals:
			self.require_vitals_before_completion = 0

		validate_registration_settings(self)
