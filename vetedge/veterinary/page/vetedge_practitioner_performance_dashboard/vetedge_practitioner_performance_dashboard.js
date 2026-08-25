frappe.pages["vetedge-practitioner-performance-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		frappe.require("vetedge_dashboard_alignment.bundle.js", function () {
			window.VetEdgeDashboardAlignment?.install?.();
			window.mountVetEdgeDashboardHost(wrapper, {
				key: "practitioner_performance",
				title: __("Practitioner Performance Dashboard"),
			});
		});
	});
};
