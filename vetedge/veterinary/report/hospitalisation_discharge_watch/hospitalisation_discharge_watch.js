frappe.query_reports["Hospitalisation Discharge Watch"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Hospitalisation Discharge Watch");
	},
	filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "care_level", label: __("Care Level"), fieldtype: "Select", options: ["", "Standard", "Observation", "Intensive Care", "ICU", "Isolation", "Recovery"] },
        { fieldname: "attending_veterinarian", label: __("Attending Veterinarian"), fieldtype: "Link", options: "User" },
        { fieldname: "minimum_days_admitted", label: __("Minimum Days Admitted"), fieldtype: "Int", default: 3 },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Admitted", "Under Care", "Ready for Discharge"] },
        { fieldname: "discharge_ready_only", label: __("Discharge Ready Only"), fieldtype: "Check" },
        { fieldname: "pending_issue_type", label: __("Pending Issue Type"), fieldtype: "Select", options: ["", "Missing Price Charges", "Pending Charge Sync", "Pending Stock Posting", "Care Location Still Assigned", "Pending Discharge Summary"] },
    ],
};
