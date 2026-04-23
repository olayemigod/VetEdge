from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from vetedge.services.owner_portal import (
	build_pagination_payload,
	create_owner_appointment_request,
	download_owner_invoice_pdf,
	generate_owner_invoice_pdf,
	get_owner_invoice,
	get_owner_appointments,
	get_owner_consultation_summaries,
	get_owner_invoices,
	get_owner_portal_dashboard,
)


class TestOwnerPortal(TestCase):
	def test_owner_can_create_appointment_request_for_own_pet(self):
		inserted = []

		def get_value(doctype, name, fields=None, **kwargs):
			if doctype == "Veterinary Patient":
				return frappe._dict(
					name="VP-001",
					primary_owner="CUST-001",
					default_branch="Main Branch",
				)
			return None

		def get_doc(values):
			doc = frappe._dict(values)
			doc.name = "VAPT-001"
			doc.appointment_title = "Bingo - 2026-04-21 10:30"
			doc.insert = lambda ignore_permissions=False: inserted.append(doc) or doc
			return doc

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=get_value,
			),
			get_doc=get_doc,
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch(
				"vetedge.services.owner_portal.get_portal_settings",
				return_value={"enable_owner_portal": True},
			),
			patch("vetedge.services.owner_portal.validate_owner_patient_access"),
			patch("vetedge.services.owner_portal.emit_notification_event", return_value={"queued": False}),
		):
			result = create_owner_appointment_request(
				patient="VP-001",
				preferred_datetime="2026-04-21T10:30",
				reason_for_visit="Follow up",
			)

		self.assertEqual(result["name"], "VAPT-001")
		self.assertEqual(result["status"], "Owner Requested")
		self.assertEqual(inserted[0].doctype, "Veterinary Appointment")
		self.assertEqual(inserted[0].patient, "VP-001")
		self.assertEqual(inserted[0].created_from, "Portal")
		self.assertEqual(inserted[0].status, "Owner Requested")

	def test_owner_appointment_request_requires_enabled_portal(self):
		frappe_stub = make_frappe_stub()

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch(
				"vetedge.services.owner_portal.get_portal_settings",
				return_value={"enable_owner_portal": False},
			),
		):
			self.assertRaises(
				frappe.PermissionError,
				create_owner_appointment_request,
				patient="VP-001",
				preferred_datetime="2026-04-21 10:30",
			)

	def test_owner_can_download_owned_invoice_pdf(self):
		response = SimpleNamespace(filename=None, filecontent=None, type=None)
		print_calls = []
		frappe_stub = make_frappe_stub(
			get_print=lambda *args, **kwargs: print_calls.append((args, kwargs)) or b"PDF",
			local=SimpleNamespace(flags=SimpleNamespace(), response=response, form_dict=SimpleNamespace()),
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=lambda doctype, name=None, fields=None, as_dict=False, **kwargs: frappe._dict(
					letter_head="Clinic Letterhead",
					company="Vet Company",
				)
				if doctype == "Sales Invoice"
				else None,
				has_column=lambda doctype, fieldname: fieldname == "default_letter_head",
			),
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch("vetedge.services.owner_portal.validate_owner_invoice_access", return_value=frappe._dict(name="SINV-001")),
		):
			download_owner_invoice_pdf("SINV-001")

		self.assertEqual(print_calls[0][1]["print_format"], "VetEdge Owner Invoice")
		self.assertEqual(print_calls[0][1]["pdf_generator"], "chrome")
		self.assertEqual(print_calls[0][1]["no_letterhead"], 0)
		self.assertEqual(print_calls[0][1]["letterhead"], "Clinic Letterhead")
		self.assertEqual(response.filename, "SINV-001.pdf")
		self.assertEqual(response.filecontent, b"PDF")
		self.assertEqual(response.type, "pdf")

	def test_owner_cannot_download_unowned_invoice_pdf(self):
		frappe_stub = make_frappe_stub(
			get_print=lambda *args, **kwargs: b"PDF",
			local=SimpleNamespace(flags=SimpleNamespace(), response=SimpleNamespace()),
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch("vetedge.services.owner_portal.validate_owner_invoice_access", side_effect=frappe.PermissionError),
		):
			self.assertRaises(frappe.PermissionError, download_owner_invoice_pdf, "SINV-OTHER")

	def test_owner_cannot_open_unowned_invoice_detail(self):
		frappe_stub = make_frappe_stub()

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch("vetedge.services.owner_portal.validate_owner_invoice_access", side_effect=frappe.PermissionError),
		):
			self.assertRaises(frappe.PermissionError, get_owner_invoice, "SINV-OTHER")

	def test_owner_pdf_download_returns_validation_error_when_pdf_engine_is_missing(self):
		frappe_stub = make_frappe_stub(
			get_print=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("pdf missing")),
			local=SimpleNamespace(flags=SimpleNamespace(), response=SimpleNamespace(), form_dict=SimpleNamespace()),
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=lambda doctype, name=None, fields=None, as_dict=False, **kwargs: frappe._dict(
					letter_head="Clinic Letterhead",
					company="Vet Company",
				)
				if doctype == "Sales Invoice"
				else None,
				has_column=lambda doctype, fieldname: fieldname == "default_letter_head",
			),
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch("vetedge.services.owner_portal.validate_owner_invoice_access", return_value=frappe._dict(name="SINV-001")),
		):
			self.assertRaises(frappe.ValidationError, download_owner_invoice_pdf, "SINV-001")

	def test_generate_owner_invoice_pdf_falls_back_to_wkhtmltopdf_after_chrome_timeout(self):
		print_calls = []

		def get_print(*args, **kwargs):
			print_calls.append((kwargs["pdf_generator"], getattr(frappe_stub.local.form_dict, "pdf_generator", None)))
			if kwargs["pdf_generator"] == "chrome":
				raise TimeoutError("Chromium took too long to start.")
			return b"PDF"

		frappe_stub = make_frappe_stub(
			get_print=get_print,
			local=SimpleNamespace(flags=SimpleNamespace(), response=SimpleNamespace(), form_dict=SimpleNamespace()),
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=lambda doctype, name=None, fields=None, as_dict=False, **kwargs: frappe._dict(
					letter_head=None,
					company="Vet Company",
				)
				if doctype == "Sales Invoice"
				else "Company Letterhead"
				if doctype == "Company"
				else None,
				has_column=lambda doctype, fieldname: fieldname == "default_letter_head",
			),
		)

		with patch("vetedge.services.owner_portal.frappe", frappe_stub):
			pdf = generate_owner_invoice_pdf("SINV-001", "VetEdge Owner Invoice")

		self.assertEqual(pdf, b"PDF")
		self.assertEqual(print_calls, [("chrome", "chrome"), ("wkhtmltopdf", "wkhtmltopdf")])

	def test_generate_owner_invoice_pdf_uses_company_default_letterhead_when_invoice_has_none(self):
		print_calls = []

		def get_print(*args, **kwargs):
			print_calls.append(kwargs)
			return b"PDF"

		frappe_stub = make_frappe_stub(
			get_print=get_print,
			local=SimpleNamespace(flags=SimpleNamespace(), response=SimpleNamespace(), form_dict=SimpleNamespace()),
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=lambda doctype, name=None, fields=None, as_dict=False, **kwargs: frappe._dict(
					letter_head=None,
					company="Vet Company",
				)
				if doctype == "Sales Invoice"
				else "Company Letterhead"
				if doctype == "Company"
				else None,
				has_column=lambda doctype, fieldname: fieldname == "default_letter_head",
			),
		)

		with patch("vetedge.services.owner_portal.frappe", frappe_stub):
			pdf = generate_owner_invoice_pdf("SINV-001", "VetEdge Owner Invoice")

		self.assertEqual(pdf, b"PDF")
		self.assertEqual(print_calls[0]["letterhead"], "Company Letterhead")

	def test_dashboard_includes_owner_profile_summary(self):
		def get_value(doctype, name, fields=None, as_dict=False, **kwargs):
			if doctype == "Customer":
				return frappe._dict(
					name="CUST-001",
					customer_name="Jane Owner",
					email_id="jane@example.com",
					mobile_no="+2348000000000",
					phone=None,
				)
			return None

		frappe_stub = make_frappe_stub(
			db=SimpleNamespace(
				exists=lambda doctype, name=None, **kwargs: True,
				get_value=get_value,
			),
			get_all=lambda *args, **kwargs: [],
			get_meta=lambda doctype: SimpleNamespace(has_field=lambda fieldname: fieldname in {"email_id", "mobile_no"}),
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch(
				"vetedge.services.owner_portal.get_owner_context",
				return_value={"user": "jane@example.com", "customers": ["CUST-001"]},
			),
			patch(
				"vetedge.services.owner_portal.get_portal_settings",
				return_value={"enable_owner_portal": True},
			),
			patch("vetedge.services.owner_portal.get_owner_pets", return_value=[]),
			patch(
				"vetedge.services.owner_portal.get_owner_appointments",
				return_value={
					"upcoming": [],
					"history": build_pagination_payload([], 0, 1, 20, "/vetedge_portal_appointments", "history_page"),
				},
			),
			patch(
				"vetedge.services.owner_portal.get_owner_invoices",
				return_value={
					"outstanding": build_pagination_payload([], 0, 1, 20, "/vetedge_portal_billing", "outstanding_page"),
					"paid": build_pagination_payload([], 0, 1, 20, "/vetedge_portal_billing", "paid_page"),
				},
			),
			patch(
				"vetedge.services.owner_portal.get_owner_consultation_summaries",
				return_value=build_pagination_payload([], 0, 1, 20, "/vetedge_portal_history", "consultation_page"),
			),
			patch("vetedge.services.owner_portal.get_portal_branches", return_value=[]),
		):
			dashboard = get_owner_portal_dashboard()

		self.assertEqual(dashboard["owner_profile"]["display_name"], "Jane Owner")
		self.assertEqual(dashboard["owner_profile"]["email"], "jane@example.com")
		self.assertEqual(dashboard["owner_profile"]["phone"], "+2348000000000")

	def test_build_pagination_payload_generates_links_and_counts(self):
		payload = build_pagination_payload(
			rows=[{"name": "ROW-1"}],
			total_count=41,
			page=2,
			page_length=20,
			path="/vetedge_portal_history",
			page_key="consultation_page",
			extra_params={"paid_page": 3},
		)

		self.assertEqual(payload["pagination"]["start_row"], 21)
		self.assertEqual(payload["pagination"]["end_row"], 40)
		self.assertEqual(payload["pagination"]["prev_url"], "/vetedge_portal_history?paid_page=3")
		self.assertEqual(payload["pagination"]["next_url"], "/vetedge_portal_history?paid_page=3&consultation_page=3")

	def test_owner_invoices_use_twenty_row_pages(self):
		get_all_calls = []

		def get_all(doctype, **kwargs):
			get_all_calls.append((doctype, kwargs))
			return []

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: None,
				count=lambda *args, **kwargs: 0,
			),
		)

		with patch("vetedge.services.owner_portal.frappe", frappe_stub):
			result = get_owner_invoices(
				owner_context={"customers": ["CUST-001"]},
				outstanding_page=2,
				paid_page=1,
				page_path="/vetedge_portal_billing",
			)

		self.assertEqual(get_all_calls[0][1]["start"], 20)
		self.assertEqual(get_all_calls[0][1]["limit"], 20)
		self.assertEqual(result["outstanding"]["pagination"]["page_length"], 20)

	def test_owner_appointment_history_uses_twenty_row_pages(self):
		get_all_calls = []

		def get_all(doctype, **kwargs):
			get_all_calls.append((doctype, kwargs))
			return []

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: None,
				count=lambda *args, **kwargs: 0,
			),
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch("vetedge.services.owner_portal.get_owner_patient_names", return_value=["VP-001"]),
			patch("vetedge.services.owner_portal.nowdate", return_value="2026-04-23"),
		):
			result = get_owner_appointments(
				owner_context={"customers": ["CUST-001"]},
				history_page=2,
				page_path="/vetedge_portal_appointments",
			)

		self.assertEqual(get_all_calls[1][1]["start"], 20)
		self.assertEqual(get_all_calls[1][1]["limit"], 20)
		self.assertEqual(result["history"]["pagination"]["page_length"], 20)

	def test_owner_consultation_history_uses_twenty_row_pages(self):
		get_all_calls = []

		def get_all(doctype, **kwargs):
			get_all_calls.append((doctype, kwargs))
			if doctype == "Veterinary Patient":
				return []
			return []

		frappe_stub = make_frappe_stub(
			get_all=get_all,
			db=SimpleNamespace(
				exists=lambda *args, **kwargs: True,
				get_value=lambda *args, **kwargs: None,
				count=lambda *args, **kwargs: 0,
			),
		)

		with (
			patch("vetedge.services.owner_portal.frappe", frappe_stub),
			patch("vetedge.services.owner_portal.get_owner_patient_names", return_value=["VP-001"]),
		):
			result = get_owner_consultation_summaries(
				owner_context={"customers": ["CUST-001"]},
				page=2,
				page_path="/vetedge_portal_history",
			)

		self.assertEqual(get_all_calls[1][1]["start"], 20)
		self.assertEqual(get_all_calls[1][1]["limit"], 20)
		self.assertEqual(result["pagination"]["page_length"], 20)


def make_frappe_stub(**overrides):
	def throw(*args, **kwargs):
		exc = args[1] if len(args) > 1 else kwargs.get("exc")
		if isinstance(exc, type) and issubclass(exc, Exception):
			raise exc()
		raise frappe.ValidationError()

	stub = SimpleNamespace(
		db=SimpleNamespace(exists=lambda *args, **kwargs: True, get_value=lambda *args, **kwargs: None),
		get_doc=lambda *args, **kwargs: None,
		get_print=lambda *args, **kwargs: b"",
		local=SimpleNamespace(flags=SimpleNamespace(), response=SimpleNamespace()),
		throw=throw,
		PermissionError=frappe.PermissionError,
		ValidationError=frappe.ValidationError,
	)
	for key, value in overrides.items():
		setattr(stub, key, value)
	return stub
