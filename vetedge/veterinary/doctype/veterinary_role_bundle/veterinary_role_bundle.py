# -*- coding: utf-8 -*-
from __future__ import annotations

from frappe.model.document import Document

from vetedge.services.permissions import validate_role_bundle


class VeterinaryRoleBundle(Document):
	def validate(self) -> None:
		validate_role_bundle(self)
