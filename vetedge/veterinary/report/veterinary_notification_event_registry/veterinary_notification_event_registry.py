# -*- coding: utf-8 -*-
from vetedge.services.notification_events import serialize_notification_events


def execute(filters=None):
	columns = [
		{"fieldname": "event_key", "label": "Event Key", "fieldtype": "Data", "width": 220},
		{"fieldname": "event_label", "label": "Event Label", "fieldtype": "Data", "width": 220},
		{"fieldname": "category", "label": "Category", "fieldtype": "Data", "width": 130},
		{"fieldname": "default_channels", "label": "Default Channels", "fieldtype": "Data", "width": 170},
		{"fieldname": "email_template", "label": "Email Template", "fieldtype": "Data", "width": 220},
		{"fieldname": "audience", "label": "Audience", "fieldtype": "Data", "width": 160},
		{"fieldname": "default_enabled", "label": "Default Enabled", "fieldtype": "Check", "width": 120},
		{"fieldname": "description", "label": "Description", "fieldtype": "Small Text", "width": 360},
	]
	rows = []
	for row in serialize_notification_events():
		row["default_channels"] = ", ".join(row["default_channels"])
		rows.append(row)
	return columns, rows
