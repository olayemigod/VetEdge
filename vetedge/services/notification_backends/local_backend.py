from __future__ import annotations

import frappe
from frappe import _


class LocalNotificationBackend:
	backend_mode = "local"
	supported_channels = ("Email", "SMS", "WhatsApp")

	def describe(self) -> dict:
		return {
			"backend_mode": self.backend_mode,
			"supported_channels": list(self.supported_channels),
			"provider_calls_enabled": False,
			"description": "Standalone VetEdge backend. Email uses Frappe/ERPNext mail delivery, while SMS and WhatsApp remain stubbed.",
		}

	def dispatch(
		self,
		event_definition,
		recipient: dict,
		channels: list[str],
		context: dict,
		settings: dict,
		reference_doctype: str | None = None,
		reference_name: str | None = None,
	) -> list[dict]:
		attempts = []
		for channel in channels:
			if channel == "Email":
				attempts.append(
					self._dispatch_email(
						event_definition=event_definition,
						recipient=recipient,
						context=context,
						reference_doctype=reference_doctype,
						reference_name=reference_name,
					)
				)
			else:
				attempts.append(
					{
						"channel": channel,
						"recipient": recipient.get("address") or recipient.get("identifier"),
						"audience_type": recipient.get("audience_type"),
						"status": "Skipped",
						"backend_mode": self.backend_mode,
						"provider_reference": None,
						"error_message": _("{0} provider is not configured in standalone VetEdge yet.").format(channel),
					}
				)
		return attempts

	def _dispatch_email(
		self,
		event_definition,
		recipient: dict,
		context: dict,
		reference_doctype: str | None = None,
		reference_name: str | None = None,
	) -> dict:
		email = recipient.get("address")
		if not email:
			return {
				"channel": "Email",
				"recipient": recipient.get("identifier"),
				"audience_type": recipient.get("audience_type"),
				"status": "Skipped",
				"backend_mode": self.backend_mode,
				"provider_reference": None,
				"error_message": _("No email address could be resolved for this recipient."),
			}

		subject, message, template_name = self._render_email(event_definition, context)
		try:
			frappe.sendmail(
				recipients=[email],
				subject=subject,
				message=message,
				delayed=True,
				raw_html=True,
				reference_doctype=reference_doctype,
				reference_name=reference_name,
			)
			return {
				"channel": "Email",
				"recipient": email,
				"audience_type": recipient.get("audience_type"),
				"status": "Queued",
				"backend_mode": self.backend_mode,
				"provider_reference": template_name,
				"error_message": None,
			}
		except Exception as exc:
			return {
				"channel": "Email",
				"recipient": email,
				"audience_type": recipient.get("audience_type"),
				"status": "Failed",
				"backend_mode": self.backend_mode,
				"provider_reference": template_name,
				"error_message": str(exc),
			}

	def _render_email(self, event_definition, context: dict) -> tuple[str, str, str | None]:
		template_name = event_definition.email_template
		if template_name and frappe.db.exists("Email Template", template_name):
			try:
				template_doc = frappe.get_doc("Email Template", template_name)
				subject = (template_doc.get_formatted_subject(context) or "").strip()
				message = (template_doc.get_formatted_response(context) or "").strip()
				if subject and message:
					return subject, message, template_name
			except Exception:
				pass

		return self._build_fallback_email(event_definition, context)

	def _build_fallback_email(self, event_definition, context: dict) -> tuple[str, str, str | None]:
		subject = f"{context.get('clinic_name') or 'VetEdge'}: {event_definition.event_label}"
		rows = []
		for key, value in (context or {}).items():
			if key in {"clinic_name", "clinic_tagline"} or value in (None, ""):
				continue
			rows.append(f"<tr><th style='text-align:left;padding:6px;border:1px solid #ddd'>{frappe.utils.escape_html(str(key).replace('_', ' ').title())}</th><td style='padding:6px;border:1px solid #ddd'>{frappe.utils.escape_html(str(value))}</td></tr>")
		message = (
			f"<p>{frappe.utils.escape_html(context.get('clinic_name') or 'VetEdge')} has an update for you.</p>"
			f"<table style='border-collapse:collapse'>{''.join(rows)}</table>"
		)
		return subject, message, None
