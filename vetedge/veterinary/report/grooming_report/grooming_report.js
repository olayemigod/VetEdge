frappe.query_reports["Grooming Report"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Grooming Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "assigned_staff", label: __("Assigned Staff"), fieldtype: "Link", options: "User" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Awaiting Payment", "Pending Grooming", "In Progress", "Completed", "Cancelled"] },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
