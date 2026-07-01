(function () {
	try {
		const labOrderStatusPalette = {
			Draft: "gray",
			Ordered: "blue",
			"Sample Collected": "orange",
			"Sent to Lab": "orange",
			"In Progress": "yellow",
			"Result Pending": "yellow",
			"Result Entered": "purple",
			"Awaiting Review": "purple",
			Reviewed: "green",
			Completed: "green",
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
