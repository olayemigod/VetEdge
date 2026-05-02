from __future__ import annotations

from frappe import _


class ProcessEdgeCoreNotificationBackend:
	backend_mode = "processedge_core"
	supported_channels = ("Email", "SMS", "WhatsApp")

	def describe(self) -> dict:
		return {
			"backend_mode": self.backend_mode,
			"supported_channels": list(self.supported_channels),
			"provider_calls_enabled": False,
			"description": "ProcessEdge Core-ready placeholder. Payloads are prepared but not transported in Phase 12B.",
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
		endpoint = settings.get("processedge_core_notification_endpoint")
		api_key = settings.get("processedge_core_notification_api_key")
		provider_reference = f"pecore::{event_definition.event_key}::{reference_doctype or 'ref'}::{reference_name or 'name'}"
		status = "Skipped"
		message = _("ProcessEdge Core notification delegation is pending transport integration.")
		if endpoint and api_key:
			message = _("ProcessEdge Core notification payload prepared, but transport integration is not connected yet.")

		return [
			{
				"channel": channel,
				"recipient": recipient.get("address") or recipient.get("identifier"),
				"audience_type": recipient.get("audience_type"),
				"status": status,
				"backend_mode": self.backend_mode,
				"provider_reference": provider_reference,
				"error_message": message,
				"backend_payload": {
					"app": "vetedge",
					"event_key": event_definition.event_key,
					"channels": list(channels),
					"recipient": recipient,
					"context": context,
					"reference_doctype": reference_doctype,
					"reference_name": reference_name,
				},
			}
			for channel in channels
		]
