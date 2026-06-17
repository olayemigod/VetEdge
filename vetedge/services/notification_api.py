from __future__ import annotations

import frappe

from vetedge.services.notification_events import get_notification_event_definition
from vetedge.services.notifications import (
	acknowledge_notification,
	archive_notification,
	dismiss_notification,
	get_notification_feed,
	get_unread_notification_count,
	mark_all_notifications_read,
	mark_notification_done,
	mark_notification_read,
	mark_notification_unread,
)


SAFE_PRIORITIES = {"Low", "Normal", "High", "Urgent"}


def _session_user() -> str:
	user = getattr(getattr(frappe, "session", None), "user", None)
	if not user or user == "Guest":
		frappe.throw("Please sign in to view Veterinary notifications.", frappe.PermissionError)
	return user


def _coerce_limit(limit: int | str | None) -> int:
	try:
		return max(1, min(int(limit or 50), 200))
	except Exception:
		return 50


def _event_category(event_key: str | None) -> str | None:
	if not event_key:
		return None
	event_definition = get_notification_event_definition(event_key)
	return event_definition.category if event_definition else None


def _normalize_notification(row) -> dict:
	get_value = row.get if hasattr(row, "get") else lambda key, default=None: getattr(row, key, default)
	event_key = get_value("event_key")
	return {
		"name": get_value("name"),
		"title": get_value("notification_title"),
		"message": get_value("message"),
		"category": _event_category(event_key),
		"priority": get_value("priority"),
		"status": get_value("status"),
		"reference_doctype": get_value("reference_doctype"),
		"reference_name": get_value("reference_name"),
		"action_url": get_value("action_url"),
		"creation": get_value("created_on") or get_value("creation"),
		"due_datetime": get_value("due_datetime"),
	}


def _filtered_items(rows: list, category: str | None = None, priority: str | None = None) -> list[dict]:
	items = []
	for row in rows:
		item = _normalize_notification(row)
		if category and item["category"] != category:
			continue
		if priority and item["priority"] != priority:
			continue
		items.append(item)
	return items


def _status_response(result: dict, user: str) -> dict:
	return {
		"ok": True,
		"notification": result.get("name"),
		"status": result.get("status"),
		"unread_count": get_unread_notification_count(user=user),
	}


@frappe.whitelist()
def get_my_notification_count() -> dict:
	user = _session_user()
	return {"unread_count": get_unread_notification_count(user=user)}


@frappe.whitelist()
def get_my_veterinary_unread_bell_count() -> dict:
	user = _session_user()
	return {"unread_count": get_veterinary_unread_bell_count(user)}


def get_veterinary_unread_bell_count(user: str) -> int:
	if not user:
		return 0
	return frappe.db.count(
		"Veterinary Notification Item",
		{
			"recipient_user": user,
			"status": "Unread",
		},
	)


@frappe.whitelist()
def mark_my_veterinary_notification_read_for_log(notification_log: str) -> dict:
	user = _session_user()
	notification_item = get_veterinary_notification_item_for_log(notification_log, user)
	if notification_item:
		mark_notification_read(notification_item, user=user)
	return {
		"ok": True,
		"notification": notification_item,
		"unread_count": get_veterinary_unread_bell_count(user),
	}


@frappe.whitelist()
def mark_all_my_veterinary_notifications_read() -> dict:
	user = _session_user()
	result = mark_all_notifications_read(user=user)
	return {
		"ok": True,
		"updated": result.get("updated", 0),
		"unread_count": get_veterinary_unread_bell_count(user),
	}


def get_veterinary_notification_item_for_log(notification_log: str | None, user: str) -> str | None:
	if not notification_log or not user:
		return None

	item_name = frappe.db.get_value(
		"Veterinary Notification Item",
		{"frappe_notification_log": notification_log, "recipient_user": user},
		"name",
	)
	if item_name:
		return item_name

	log = frappe.db.get_value(
		"Notification Log",
		{"name": notification_log, "for_user": user},
		["document_type", "document_name", "subject", "link"],
		as_dict=True,
	)
	if not log:
		return None
	if log.get("document_type") == "Veterinary Notification Item":
		return frappe.db.get_value(
			"Veterinary Notification Item",
			{"name": log.get("document_name"), "recipient_user": user},
			"name",
		)

	filters = {
		"recipient_user": user,
		"notification_title": log.get("subject"),
		"reference_doctype": log.get("document_type"),
		"reference_name": log.get("document_name"),
	}
	if log.get("link"):
		filters["action_url"] = log.get("link")
	return frappe.db.get_value("Veterinary Notification Item", filters, "name")


@frappe.whitelist()
def get_my_notifications(
	status: str | None = None,
	category: str | None = None,
	priority: str | None = None,
	limit: int | str = 50,
) -> dict:
	user = _session_user()
	if priority and priority not in SAFE_PRIORITIES:
		frappe.throw("Priority filter is not valid.", frappe.ValidationError)

	rows = get_notification_feed(
		user=user,
		status=status,
		include_archived=False,
		limit=_coerce_limit(limit),
	)
	return {
		"items": _filtered_items(rows, category=category, priority=priority),
		"unread_count": get_unread_notification_count(user=user),
	}


@frappe.whitelist()
def mark_my_notification_read(notification_name: str) -> dict:
	user = _session_user()
	return _status_response(mark_notification_read(notification_name, user=user), user)


@frappe.whitelist()
def mark_my_notification_unread(notification_name: str) -> dict:
	user = _session_user()
	return _status_response(mark_notification_unread(notification_name, user=user), user)


@frappe.whitelist()
def acknowledge_my_notification(notification_name: str) -> dict:
	user = _session_user()
	return _status_response(acknowledge_notification(notification_name, user=user), user)


@frappe.whitelist()
def mark_my_notification_done(notification_name: str) -> dict:
	user = _session_user()
	return _status_response(mark_notification_done(notification_name, user=user), user)


@frappe.whitelist()
def dismiss_my_notification(notification_name: str) -> dict:
	user = _session_user()
	return _status_response(dismiss_notification(notification_name, user=user), user)


@frappe.whitelist()
def archive_my_notification(notification_name: str) -> dict:
	user = _session_user()
	return _status_response(archive_notification(notification_name, user=user), user)


@frappe.whitelist()
def mark_all_my_notifications_read() -> dict:
	user = _session_user()
	mark_all_notifications_read(user=user)
	return {
		"ok": True,
		"status": "Read",
		"unread_count": get_unread_notification_count(user=user),
	}
