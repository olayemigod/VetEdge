from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import TestCase

from vetedge.setup.email_templates import _build_template_payload


FIXTURE_PATH = Path("/home/olayemigod/frappe-bench/apps/vetedge/fixtures/vetedge_email_templates.json")
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)")
SUPPORTED_PLACEHOLDERS = {
	"action",
	"actual_check_out_date",
	"administered_on",
	"amount",
	"applied_by",
	"appointment_datetime",
	"available_qty",
	"batch_no",
	"branch",
	"check_in_date",
	"clinic_name",
	"clinic_tagline",
	"complaint_subject",
	"consultation",
	"expected_check_out_date",
	"expiry_date",
	"grooming_service",
	"invoice",
	"item",
	"kennel",
	"lab_order",
	"next_due_date",
	"owner_name",
	"patient_name",
	"practitioner",
	"reason",
	"record",
	"required_qty",
	"role_bundle",
	"staff_name",
	"user",
	"vaccine",
	"warehouse",
}


class TestEmailTemplateStructure(TestCase):
	def test_fixture_contains_email_templates(self):
		rows = json.loads(FIXTURE_PATH.read_text())
		self.assertGreater(len(rows), 0)
		self.assertTrue(all(row.get("doctype") == "Email Template" for row in rows))

	def test_fixture_template_names_are_unique(self):
		rows = json.loads(FIXTURE_PATH.read_text())
		names = [row.get("name") for row in rows]
		self.assertEqual(len(names), len(set(names)))

	def test_fixture_contains_key_vetedge_templates(self):
		rows = json.loads(FIXTURE_PATH.read_text())
		names = {row.get("name") for row in rows}
		for template_name in (
			"VetEdge - Appointment Created",
			"VetEdge - Payment Received",
			"VetEdge - Lab Order Created",
			"VetEdge - Vaccination Administered",
			"VetEdge - Boarding Checked In",
			"VetEdge - Grooming Completed",
		):
			self.assertIn(template_name, names)

	def test_fixture_placeholders_match_supported_vetedge_context_keys(self):
		rows = json.loads(FIXTURE_PATH.read_text())
		placeholders = set()
		for row in rows:
			text = (row.get("subject") or "") + "\n" + (row.get("response") or "")
			placeholders.update(PLACEHOLDER_PATTERN.findall(text))
		self.assertTrue(placeholders.issubset(SUPPORTED_PLACEHOLDERS), placeholders - SUPPORTED_PLACEHOLDERS)

	def test_html_fixture_templates_seed_into_response_html(self):
		rows = json.loads(FIXTURE_PATH.read_text())
		first_html = next(row for row in rows if row.get("use_html"))
		payload = _build_template_payload(first_html)
		self.assertTrue(payload.get("response_html"))
		self.assertEqual(payload.get("response"), "")
