frappe.listview_settings["Veterinary Hospitalisation"] = {
	add_fields: ["status", "patient", "customer", "service_branch", "admission_datetime", "payment_gate_status"],
	get_indicator(doc) {
		const colors = {
			Draft: "gray",
			Admitted: "blue",
			"Under Care": "orange",
			"Ready for Discharge": "purple",
			Discharged: "green",
			Cancelled: "red",
		};
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
