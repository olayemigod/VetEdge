# -*- coding: utf-8 -*-
from __future__ import annotations

import json

import frappe
from frappe.model.document import Document
from frappe.utils import cint, getdate


class VeterinaryLicenseProfile(Document):
	def validate(self) -> None:
		self.plan_name = (self.plan_name or "").strip()
		self.validate_dates()
		self.validate_limits()
		self.validate_enabled_modules()

	def validate_dates(self) -> None:
		if self.start_date and self.expiry_date and getdate(self.expiry_date) < getdate(self.start_date):
			frappe.throw("Expiry Date cannot be before Start Date.", frappe.ValidationError)

	def validate_limits(self) -> None:
		if self.max_branches not in (None, "") and cint(self.max_branches) < 0:
			frappe.throw("Max Branches cannot be negative.", frappe.ValidationError)

		if self.max_users not in (None, "") and cint(self.max_users) < 0:
			frappe.throw("Max Users cannot be negative.", frappe.ValidationError)

	def validate_enabled_modules(self) -> None:
		if not self.enabled_modules:
			self.enabled_modules = "[]"
			return

		try:
			modules = json.loads(self.enabled_modules)
		except ValueError:
			frappe.throw("Enabled Modules must be valid JSON.", frappe.ValidationError)

		if not isinstance(modules, list):
			frappe.throw("Enabled Modules must be a JSON array.", frappe.ValidationError)
