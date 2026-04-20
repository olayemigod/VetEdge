frappe.listview_settings["Veterinary Appointment"] = {
	get_indicator(doc) {
		const color = {
			"Awaiting Registration": "gray",
			"Owner Requested": "orange",
			Scheduled: "blue",
			Confirmed: "green",
			"Checked In": "yellow",
			"In Consultation": "purple",
			Completed: "green",
			Rescheduled: "orange",
			Cancelled: "red",
			"No Show": "gray",
		}[doc.status] || "gray";

		return [__(doc.status), color, `status,=,${doc.status}`];
	},
};
