(function () {
	const existing = frappe.listview_settings["Veterinary Vital Signs"] || {};
	const originalOnload = existing.onload;
	frappe.listview_settings["Veterinary Vital Signs"] = {
		...existing,
		onload(listview) {
			if (typeof originalOnload === "function") originalOnload(listview);
			if (window.location.pathname === "/app/vetedge-clinical-workspace") return;
			window.location.replace("/app/vetedge-clinical-workspace?tab=vitals");
		},
	};
})();
