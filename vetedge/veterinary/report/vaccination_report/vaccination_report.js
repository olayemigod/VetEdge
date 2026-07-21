frappe.query_reports["Vaccination Report"] = {
	onload(report) {
		window.vetedgeReportEdgeUI?.register("Vaccination Report", {
			eyebrow: __("Preventive Care"),
			title: __("Vaccination Report"),
			subtitle: __("Review scheduled, administered, due-soon, overdue, payment-pending, and cancelled vaccination activity across the selected branch."),
			emptyDescription: __("Adjust the date, branch, vaccine, status, due status, patient, owner, or practitioner filters."),
		});
		window.vetedgeReportVisibility?.apply(report, "Vaccination Report");
		window.vetedgeReportEdgeUI?.attach(report, "Vaccination Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "vaccine", label: __("Vaccine"), fieldtype: "Link", options: "Veterinary Vaccine" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Awaiting Payment", "Pending Administration", "Administered", "Cancelled"] },
		{ fieldname: "due_status", label: __("Due Status"), fieldtype: "Select", options: ["", "Due Soon", "Overdue", "Administered"] },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "practitioner", label: __("Practitioner"), fieldtype: "Link", options: "User" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
