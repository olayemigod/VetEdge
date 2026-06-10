frappe.query_reports["Revenue Summary"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Revenue Summary");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "cost_center", label: __("Cost Center"), fieldtype: "Link", options: "Cost Center" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "service_category", label: __("Service Category"), fieldtype: "Select", options: ["", "Consultation", "Lab", "Vaccination", "Boarding", "Grooming", "Dispensary", "Registration", "General"] },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Paid", "Unpaid", "Overdue", "Cancelled"] },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
