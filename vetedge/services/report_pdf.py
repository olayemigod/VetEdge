from __future__ import annotations

import frappe
from frappe import _
from frappe.utils.pdf import get_chrome_pdf, get_pdf


def _build_pdf_options(orientation: str | None = None) -> dict:
	options = {}
	if orientation:
		options["orientation"] = orientation
	return options


def _set_pdf_download_response(pdf_bytes: bytes, report_name: str | None = None) -> None:
	frappe.local.response.filename = f"{(report_name or 'report').replace('/', '-')}.pdf"
	frappe.local.response.filecontent = pdf_bytes
	frappe.local.response.type = "download"
	frappe.local.response.content_type = "application/pdf"
	frappe.local.response.display_content_as = "attachment"


@frappe.whitelist()
def download_report_pdf(
	html: str,
	orientation: str = "Landscape",
	report_name: str | None = None,
) -> None:
	if not html:
		frappe.throw(_("Report content is required for PDF generation."))

	options = _build_pdf_options(orientation)
	last_error = None

	try:
		chrome_pdf = get_chrome_pdf(
			print_format=None,
			html=html,
			options=options.copy(),
			output=None,
			pdf_generator="chrome",
		)
		if chrome_pdf:
			_set_pdf_download_response(chrome_pdf, report_name=report_name)
			return
	except Exception as exc:
		last_error = exc
		frappe.log_error(
			title="VetEdge Report PDF Chrome Fallback Failed",
			message=frappe.get_traceback(),
		)

	try:
		pdf_bytes = get_pdf(html, options=options)
		_set_pdf_download_response(pdf_bytes, report_name=report_name)
		return
	except Exception as exc:
		last_error = exc
		frappe.log_error(
			title="VetEdge Report PDF Wkhtmltopdf Failed",
			message=frappe.get_traceback(),
		)

	frappe.throw(
		_("Report PDF generation failed. Please check the server PDF generator configuration.")
	)
