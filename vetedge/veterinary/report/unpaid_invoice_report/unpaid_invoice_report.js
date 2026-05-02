frappe.query_reports["Unpaid Invoice Report"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Unpaid Invoice Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "age_range", label: __("Age Range"), fieldtype: "Select", options: ["", "0-30", "31-60", "61-90", "90+"] },
	],
};
