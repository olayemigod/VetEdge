frappe.query_reports["Kennel Availability Report"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Kennel Availability Report");
	},
	filters: [
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), 7) },
		{ fieldname: "kennel", label: __("Kennel"), fieldtype: "Link", options: "Kennel" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Available", "Reserved", "Occupied", "Full", "Out of Service / Inactive"] },
	],
};
