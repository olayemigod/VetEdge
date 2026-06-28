frappe.query_reports["Stock Expiry Status"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Stock Expiry Status");
	},
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company" },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "warehouse", label: __("Warehouse"), fieldtype: "Link", options: "Warehouse" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "expiry_buckets", label: __("Expiry Buckets"), fieldtype: "Data", default: "30,60,90" },
		{ fieldname: "include_zero_qty", label: __("Include Zero Qty"), fieldtype: "Check", default: 0 },
	],
};
