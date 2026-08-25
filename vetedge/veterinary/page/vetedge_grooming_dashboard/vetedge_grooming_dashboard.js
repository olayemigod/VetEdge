frappe.pages["vetedge-grooming-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		frappe.require("vetedge_dashboard_alignment.bundle.js", function () {
			window.VetEdgeDashboardAlignment?.install?.();
			window.mountVetEdgeDashboardHost(wrapper, {
				key: "grooming",
				title: __("Grooming Dashboard"),
			});
		});
	});
};
