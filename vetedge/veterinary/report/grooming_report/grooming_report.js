frappe.query_reports["Grooming Report"] = {
	onload(report) {
		window.vetedgeReportEdgeUI?.register("Grooming Report", {
			eyebrow: __("Grooming Operations"),
			title: __("Grooming Report"),
			subtitle: __("Review bookings, assigned staff, payment state, work in progress, completed sessions, service value, and cancelled appointments."),
			emptyDescription: __("Adjust the date, branch, assigned staff, status, patient, or owner filters and refresh the report."),
		});
		window.vetedgeReportVisibility?.apply(report, "Grooming Report");
		window.vetedgeReportEdgeUI?.attach(report, "Grooming Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "assigned_staff", label: __("Assigned Staff"), fieldtype: "Link", options: "User" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Awaiting Payment", "Pending Grooming", "In Progress", "Completed", "Cancelled"] },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
