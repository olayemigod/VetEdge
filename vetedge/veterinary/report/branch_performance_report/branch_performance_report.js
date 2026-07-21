frappe.query_reports["Branch Performance Report"] = {
	onload(report) {
		window.vetedgeReportEdgeUI?.register("Branch Performance Report", {
			eyebrow: __("Management Report"),
			title: __("Branch Performance"),
			subtitle: __("Compare consultations, appointments, revenue, outstanding balances, laboratory, vaccination, dispensary, grooming, and boarding activity by branch."),
			emptyDescription: __("Choose another date range or confirm that the selected branches have operational and billing activity."),
		});
		window.vetedgeReportVisibility?.apply(report, "Branch Performance Report");
		window.vetedgeReportEdgeUI?.attach(report, "Branch Performance Report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
