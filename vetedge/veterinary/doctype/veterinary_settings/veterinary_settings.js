frappe.ui.form.on("Veterinary Settings", {
	setup() {
		if (window.location.pathname !== "/desk/veterinary-settings-center") {
			window.location.replace("/desk/veterinary-settings-center");
		}
	},
	refresh() {
		if (window.location.pathname !== "/desk/veterinary-settings-center") {
			window.location.replace("/desk/veterinary-settings-center");
		}
	},
});
