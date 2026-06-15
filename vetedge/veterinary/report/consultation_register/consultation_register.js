frappe.query_reports["Consultation Register"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Consultation Register");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "practitioner", label: __("Practitioner"), fieldtype: "Link", options: "User" },
		{ fieldname: "consultation_type", label: __("Consultation Type"), fieldtype: "Link", options: "Consultation Type" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "In Progress", "Awaiting Payment", "Ready for Treatment", "Completed", "Cancelled"] },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
