(function () {
	try {
		const consultationStatusPalette = {
			Draft: "gray",
			"In Progress": "blue",
			"Awaiting Payment": "orange",
			"Pending Dispensary": "yellow",
			"Ready for Treatment": "purple",
			Completed: "green",
			Cancelled: "red",
		};

		frappe.listview_settings["Veterinary Consultation"] = {
			onload() {
				window.location.replace("/app/vetedge-clinical-workspace");
			},
			get_indicator(doc) {
				const status = doc.status || "Unknown";
				const color = consultationStatusPalette[status] || "gray";
				return [__(status), color, `status,=,${status}`];
			},
		};
	} catch (error) {
		console.error("VetEdge consultation list routing failed", error);
	}
})();
