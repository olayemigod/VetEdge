frappe.query_reports["Owner Register"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Owner Register");
	},
	filters: [
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "outstanding_only", label: __("Outstanding Only"), fieldtype: "Check", default: 0 },
	],
};
