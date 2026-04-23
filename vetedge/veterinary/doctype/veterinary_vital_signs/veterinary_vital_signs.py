from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.copy_control import reset_vetedge_copy_state
from vetedge.services.vitals import validate_vital_signs


class VeterinaryVitalSigns(Document):
	def validate(self) -> None:
		reset_vetedge_copy_state(self)
		validate_vital_signs(self)
