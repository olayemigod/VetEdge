frappe.query_reports["Active Hospitalisations"] = {
	onload(report) {
		window.vetedgeReportVisibility?.apply(report, "Active Hospitalisations");
	},
	filters: [
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "care_level", label: __("Care Level"), fieldtype: "Select", options: ["", "Standard", "Observation", "Intensive Care", "ICU", "Isolation", "Recovery"] },
        { fieldname: "care_location", label: __("Care Location"), fieldtype: "Link", options: "Veterinary Care Location" },
        { fieldname: "attending_veterinarian", label: __("Attending Veterinarian"), fieldtype: "Link", options: "User" },
        { fieldname: "status", label: __("Status"), fieldtype: "Select", options: ["", "Admitted", "Under Care", "Ready for Discharge", "Discharged", "Cancelled"] },
        { fieldname: "admission_date_from", label: __("Admission Date From"), fieldtype: "Date" },
        { fieldname: "admission_date_to", label: __("Admission Date To"), fieldtype: "Date" },
        { fieldname: "owner", label: __("Pet Owner"), fieldtype: "Link", options: "Customer" },
        { fieldname: "patient", label: __("Patient"), fieldtype: "Link", options: "Veterinary Patient" },
    ],
};
