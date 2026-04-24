(function () {
	try {
		const labOrderStatusPalette = {
			Draft: "gray",
			Requested: "blue",
			"Sample Collected": "orange",
			"In Progress": "yellow",
			"Result Entered": "purple",
			Reviewed: "green",
			Cancelled: "red",
		};

		frappe.listview_settings["Veterinary Lab Order"] = {
			get_indicator(doc) {
				const status = doc.status || "Unknown";
				const color = labOrderStatusPalette[status] || "gray";
				return [__(status), color, `status,=,${status}`];
			},
		};
	} catch (error) {
		console.error("VetEdge lab order list indicator setup failed", error);
	}
})();
