from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.permissions import validate_branch_practitioner_assignment


class BranchPractitionerAssignment(Document):
	def validate(self) -> None:
		validate_branch_practitioner_assignment(self)
