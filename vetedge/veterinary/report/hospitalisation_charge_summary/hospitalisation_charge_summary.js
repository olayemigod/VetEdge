frappe.query_reports["Hospitalisation Charge Summary"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Hospitalisation Charge Summary");
	},
	filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
        { fieldname: "care_level", label: __("Care Level"), fieldtype: "Select", options: ["", "Standard", "Observation", "Intensive Care", "ICU", "Isolation", "Recovery"] },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Draft", "Admitted", "Under Care", "Ready for Discharge", "Discharged", "Cancelled"] },
        { fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
        { fieldname: "owner", label: __("Pet Owner"), fieldtype: "Link", options: "Customer" },
        { fieldname: "invoice_status", label: __("Invoice Status"), fieldtype: "Select", options: ["", "Not Invoiced", "Draft", "Unpaid", "Partly Paid", "Paid", "Overdue", "Cancelled"] },
        { fieldname: "missing_price_only", label: __("Missing Price Only"), fieldtype: "Check" },
        { fieldname: "pending_only", label: __("Pending Only"), fieldtype: "Check" },
    ],
};
