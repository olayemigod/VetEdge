# Veterinary Notifications: Frappe Bell Audit

Date: 2026-06-15

## Installed Frappe Behavior

The installed Frappe Desk notification surface is implemented by:

- `frappe/desk/doctype/notification_log/notification_log.py`
- `frappe/public/js/frappe/ui/notifications/notifications.js`
- `frappe/public/js/frappe/ui/sidebar/sidebar.js`
- `frappe/desk/doctype/notification_settings/notification_settings.py`

Desk creates a standard sidebar notification button labelled `Notification`. The dropdown is populated by `frappe.desk.doctype.notification_log.notification_log.get_notification_logs`, which reads recent `Notification Log` records visible to the current user.

`Notification Log.after_insert` publishes the realtime event `notification` for `for_user` and sets `Notification Settings.seen = 0`. The Desk listener for `notification` toggles the notification icon to the unseen state and fetches the latest log row into the dropdown.

## Fields Used By Desk

The dropdown uses these `Notification Log` fields:

- `subject` for display text
- `for_user` for recipient scoping
- `read` for unread row styling
- `from_user` for avatar/user info
- `document_type` and `document_name` for default form links
- `link` as an explicit route override
- `creation` for timestamp display

`type = Alert` is valid for in-app alerts. Frappe suppresses notification email for `Alert`.

## Unread And Indicator Behavior

This installed Desk UI does not show a numeric unread count badge for `Notification Log`.

It supports:

- an unseen indicator on the notification icon, driven by `Notification Settings.seen`
- unread styling per dropdown row, driven by `Notification Log.read`
- `mark_as_read` and `mark_all_as_read` APIs

Opening the dropdown sets `Notification Settings.seen = 1` and hides the indicator. That does not automatically mark every `Notification Log.read` row as read; row read state is handled separately.

## Realtime Behavior

`frappe.publish_realtime("notification", user=...)` is the Desk event that refreshes the notification dropdown and shows the unseen indicator. Creating a `Notification Log` through normal document insert already triggers this in `NotificationLog.after_insert`.

Publishing the event manually can refresh the Desk UI, but it is not a substitute for creating a valid `Notification Log` row.

## Is Notification Log Mirroring Enough?

Mirroring Veterinary notifications into `Notification Log` is enough for them to appear in the native Desk notification dropdown when:

- the row is created for the correct `for_user`
- user notifications are enabled
- `subject` is set
- `document_type`/`document_name` or `link` points to the desired target
- the Desk client receives `notification` realtime or reloads the list

It is not enough if the product requirement is a numeric unread bubble/count. This Frappe version provides an unseen indicator and unread row styling, not a dedicated numeric count badge.

## Recommendation

Use a hybrid direction if a visible Veterinary count remains required:

- keep `Veterinary Notification Item` as the durable operational record
- keep mirroring into Frappe `Notification Log` for native Desk history, routing, read state, and realtime refresh
- add only a small custom Veterinary unread count indicator near the native notification area if the clinic workflow requires a numeric count

Do not build another full drawer while the native dropdown already handles recent notification display and routing.
