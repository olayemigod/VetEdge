frappe.query_reports["Lab Order Report"] = {
	onload(report) {
		window.vetedgeReportEdgeUI?.register("Lab Order Report", {
			eyebrow: __("Laboratory Operations"),
			title: __("Laboratory Report"),
			subtitle: __("Track requests, sample collection, processing, result entry, clinical review, billing readiness, and patient follow-up."),
			emptyDescription: __("Adjust the date, branch, status, practitioner, or patient filters and refresh the report."),
		});
		window.vetedgeReportVisibility?.apply(report, "Lab Order Report");
		window.vetedgeReportEdgeUI?.attach(report, "Lab Order Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Requested", "Sample Collected", "In Progress", "Result Entered", "Reviewed", "Cancelled"] },
		{ fieldname: "practitioner", label: __("Practitioner"), fieldtype: "Link", options: "User" },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
