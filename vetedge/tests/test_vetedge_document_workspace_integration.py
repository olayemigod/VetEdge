from __future__ import annotations

import frappe
import frappe.model.workflow as workflow_module
from frappe.tests.utils import FrappeTestCase

from vetedge.services.document_workspace import (
	get_document,
	get_document_list,
	get_resource_definition,
)


class TestVetEdgeDocumentWorkspaceIntegration(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_resource_definitions_are_permission_aware_and_complete(self):
		for resource, doctype in (
			("patients", "Veterinary Patient"),
			("appointments", "Veterinary Appointment"),
			("settings", "Veterinary Settings"),
		):
			definition = get_resource_definition(resource)
			self.assertEqual(definition["resource"], resource)
			self.assertEqual(definition["doctype"], doctype)
			self.assertTrue(definition["permissions"]["read"])

	def test_new_patient_and_appointment_forms_resolve_real_metadata(self):
		for resource in ("patients", "appointments"):
			payload = get_document(resource)
			self.assertTrue(payload["is_new"])
			self.assertFalse(payload["is_single"])
			self.assertTrue(payload["schema"]["tabs"])
			self.assertIsInstance(payload["values"], dict)
			self.assertIn("permissions", payload)

	def test_frappe_16_workflow_state_field_compatibility(self):
		for resource, doctype in (
			("patients", "Veterinary Patient"),
			("appointments", "Veterinary Appointment"),
		):
			meta = frappe.get_meta(doctype)
			self.assertTrue(hasattr(meta, "workflow_state_field"))
			self.assertEqual(meta.workflow_state_field, "")

			payload = get_document(resource)
			self.assertEqual(payload["state_field"], "status")

	def test_plain_status_documents_do_not_raise_workflow_not_found_popup(self):
		class PlainVeterinaryPatient:
			doctype = "Veterinary Patient"

		frappe.clear_messages()
		self.assertEqual(workflow_module.get_transitions(PlainVeterinaryPatient()), [])
		messages = [str(message.get("message") or "") for message in frappe.get_message_log()]
		self.assertFalse(any("Workflow not found" in message for message in messages))

	def test_veterinary_settings_resolve_as_grouped_single_document(self):
		payload = get_document("settings")
		self.assertFalse(payload["is_new"])
		self.assertTrue(payload["is_single"])
		self.assertEqual(payload["doctype"], "Veterinary Settings")
		self.assertGreaterEqual(len(payload["schema"]["tabs"]), 2)
		self.assertIsInstance(payload["values"], dict)

	def test_permission_aware_lists_return_pagination_contract(self):
		for resource in ("patients", "appointments"):
			payload = get_document_list(resource, page_length=5)
			for key in ("rows", "total", "start", "page_length"):
				self.assertIn(key, payload)
			self.assertEqual(payload["start"], 0)
			self.assertEqual(payload["page_length"], 5)
