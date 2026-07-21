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
		{
			fieldname: "income_category",
			label: __("Income Category"),
			fieldtype: "Select",
			options: [
				"",
				"Consultation Service Income",
				"Treatment Income",
				"Laboratory Income",
				"Vaccination Income",
				"Grooming Income",
				"Boarding Income",
				"Hospitalisation Income",
				"Dispensary Income",
				"Registration Income",
				"Other Income",
			],
		},
		{
			fieldname: "service_category",
			label: __("Legacy Service Source"),
			fieldtype: "Select",
			options: ["", "Consultation", "Lab", "Vaccination", "Grooming", "Boarding", "Hospitalisation", "Dispensary", "Registration", "General"],
			description: __("Compatibility filter for older invoice source classification."),
		},
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Paid", "Unpaid", "Overdue"] },
		{ fieldname: "chart", label: __("Chart"), fieldtype: "Data", hidden: 1 },
	],
};
