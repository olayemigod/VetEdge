import frappe


FIELDS = (
	{
		"fieldname": "enable_reporting_print",
		"label": "Enable Report & Dashboard Printing",
		"fieldtype": "Check",
		"default": "1",
		"depends_on": "eval:doc.enable_vetedge",
		"description": "Master switch for Print actions on VetEdge reports and dashboards. User report/dashboard access and action permission are still required.",
		"insert_after": "enable_advanced_reports",
	},
	{
		"fieldname": "enable_reporting_export",
		"label": "Enable Report & Dashboard Export",
		"fieldtype": "Check",
		"default": "1",
		"depends_on": "eval:doc.enable_vetedge",
		"description": "Master switch for downloadable report/dashboard exports. User report/dashboard access and action permission are still required; server-side checks remain authoritative.",
		"insert_after": "enable_reporting_print",
	},
)


def execute():
	if not frappe.db.exists("DocType", "Veterinary Settings"):
		return

	for field in FIELDS:
		name = f"Veterinary Settings-{field['fieldname']}"
		if frappe.db.exists("Custom Field", name):
			continue
		frappe.get_doc({"doctype": "Custom Field", "dt": "Veterinary Settings", **field}).insert()
