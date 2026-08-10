frappe.ui.form.on("Veterinary Settings", {
	setup() {
		if (window.location.pathname !== "/app/veterinary-settings-center") {
			window.location.replace("/app/veterinary-settings-center");
		}
	},
	refresh() {
		if (window.location.pathname !== "/app/veterinary-settings-center") {
			window.location.replace("/app/veterinary-settings-center");
		}
	},
});
