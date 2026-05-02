from __future__ import annotations


class LocalNotificationBackend:
	backend_mode = "local"
	supported_channels = ("Email", "SMS", "WhatsApp")

	def describe(self) -> dict:
		return {
			"backend_mode": self.backend_mode,
			"supported_channels": list(self.supported_channels),
			"provider_calls_enabled": False,
			"description": "Standalone VetEdge backend placeholder. Existing local notification code continues to handle dispatch.",
		}
