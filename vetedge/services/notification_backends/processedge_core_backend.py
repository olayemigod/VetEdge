from __future__ import annotations


class ProcessEdgeCoreNotificationBackend:
	backend_mode = "processedge_core"
	supported_channels = ("Email", "SMS", "WhatsApp")

	def describe(self) -> dict:
		return {
			"backend_mode": self.backend_mode,
			"supported_channels": list(self.supported_channels),
			"provider_calls_enabled": False,
			"description": "ProcessEdge Core-ready placeholder. Provider routing and dispatch delegation will be implemented in a later phase.",
		}
