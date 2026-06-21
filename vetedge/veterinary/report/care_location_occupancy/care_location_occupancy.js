frappe.query_reports["Care Location Occupancy"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Care Location Occupancy");
	},
	filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "location_type", label: __("Location Type"), fieldtype: "Select", options: ["", "Ward", "Kennel", "Cage", "ICU", "Isolation", "Recovery", "General"] },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Available", "Occupied", "Cleaning", "Maintenance", "Inactive"] },
        { fieldname: "include_inactive", label: __("Include Inactive"), fieldtype: "Check" },
        { fieldname: "occupied_only", label: __("Occupied Only"), fieldtype: "Check" },
    ],
};
