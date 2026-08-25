frappe.query_reports["Service Revenue Breakdown"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Revenue Summary");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "practitioner", label: __("Practitioner"), fieldtype: "Data" },
		{
			fieldname: "service_category",
			label: __("Service Category"),
			fieldtype: "Select",
			options: [
				"",
				"Consultation Service",
				"Treatment",
				"Registration",
				"Vaccination",
				"Lab",
				"Grooming",
				"Boarding",
				"Hospitalisation",
				"Dispensary / Pharmacy",
				"General / Other",
			],
		},
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
	],
};
