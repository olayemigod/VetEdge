from vetedge.services.notification_backends.local_backend import LocalNotificationBackend
from vetedge.services.notification_backends.processedge_core_backend import (
	ProcessEdgeCoreNotificationBackend,
)


def get_notification_backend(mode: str = "local"):
	if mode == "processedge_core":
		return ProcessEdgeCoreNotificationBackend()
	return LocalNotificationBackend()
