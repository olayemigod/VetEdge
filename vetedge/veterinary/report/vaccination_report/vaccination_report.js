frappe.query_reports["Vaccination Report"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Vaccination Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "vaccine", label: __("Vaccine"), fieldtype: "Link", options: "Veterinary Vaccine" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Awaiting Payment", "Pending Administration", "Administered", "Cancelled"] },
		{ fieldname: "due_status", label: __("Due Status"), fieldtype: "Select", options: ["", "Due Soon", "Overdue", "Administered"] },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
