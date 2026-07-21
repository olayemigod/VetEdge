frappe.query_reports["Boarding Report"] = {
	onload(report) {
		window.vetedgeReportEdgeUI?.register("Boarding Report", {
			eyebrow: __("Boarding Operations"),
			title: __("Boarding Report"),
			subtitle: __("Track reservations, active stays, kennel assignment, stay duration, billing value, outstanding actions, and completed check-outs."),
			emptyDescription: __("Adjust the date, branch, kennel, status, patient, or owner filters and refresh the report."),
		});
		window.vetedgeReportVisibility?.apply(report, "Boarding Report");
		window.vetedgeReportEdgeUI?.attach(report, "Boarding Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "kennel", label: __("Kennel"), fieldtype: "Link", options: "Kennel" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Reserved", "Checked In", "Checked Out", "Cancelled"] },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
