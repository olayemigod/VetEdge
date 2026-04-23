from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.permissions import validate_branch_user_assignment


class BranchUserAssignment(Document):
	def validate(self) -> None:
		validate_branch_user_assignment(self)
