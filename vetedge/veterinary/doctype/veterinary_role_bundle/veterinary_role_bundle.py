# -*- coding: utf-8 -*-
from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.role_bundle_security import validate_role_bundle_document


class VeterinaryRoleBundle(Document):
	def validate(self) -> None:
		validate_role_bundle_document(self)
