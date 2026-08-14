frappe.query_reports["Planned Treatment"] = {
	onload() {
		window.location.replace("/desk/vetedge-treatment-plan-report");
	},
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.add_days(frappe.datetime.get_today(), -30) },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today() },
		{ fieldname: "branch", label: __("Service Branch"), fieldtype: "Link", options: "Branch" },
		{ fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
		{ fieldname: "owner", label: __("Owner"), fieldtype: "Link", options: "Customer" },
		{ fieldname: "practitioner", label: __("Practitioner"), fieldtype: "Link", options: "User" },
		{ fieldname: "consultation_type", label: __("Consultation Type"), fieldtype: "Link", options: "Consultation Type" },
		{ fieldname: "item", label: __("Treatment Item / Service"), fieldtype: "Link", options: "Item" },
		{
			fieldname: "consultation_status",
			label: __("Consultation Status"),
			fieldtype: "Select",
			options: ["", "Draft", "In Progress", "Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled"],
		},
	],
};