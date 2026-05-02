frappe.query_reports["Practitioner Performance Report"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Practitioner Performance Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "practitioner", label: __("Practitioner"), fieldtype: "Link", options: "User" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
