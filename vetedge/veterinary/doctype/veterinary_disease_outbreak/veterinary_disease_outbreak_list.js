frappe.listview_settings["Veterinary Disease Outbreak"] = {
	onload() {
		const route = frappe.get_route?.() || [];
		if (route[0] !== "List" || route[1] !== "Veterinary Disease Outbreak") return;
		frappe.set_route?.("vetedge-disease-outbreak-register");
	},
};
