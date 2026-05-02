frappe.query_reports["Patient Register"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Patient Register");
	},
	filters: [
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "species", label: __("Species"), fieldtype: "Link", options: "Veterinary Species" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "registration_status", label: __("Registration Status"), fieldtype: "Data" },
	],
};
