frappe.pages["vetedge-lab-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		frappe.require("vetedge_dashboard_alignment.bundle.js", function () {
			window.VetEdgeDashboardAlignment?.install?.();
			window.mountVetEdgeDashboardHost(wrapper, {
				key: "lab",
				title: __("Lab Dashboard"),
			});
		});
	});
};
