frappe.query_reports["Pending Hospitalisation Actions"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Pending Hospitalisation Actions");
	},
	filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "action_type", label: __("Action Type"), fieldtype: "Select", options: ["", "Missing Price Charges", "Pending Charge Sync", "Pending Stock Posting", "Care Location Still Assigned", "No Recent Activity", "Pending Discharge Summary", "Pending Daily Charges"] },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Admitted", "Under Care", "Ready for Discharge"] },
        { fieldname: "attending_veterinarian", label: __("Assigned To / Attending Veterinarian"), fieldtype: "Link", options: "User" },
        { fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
        { fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
    ],
};
