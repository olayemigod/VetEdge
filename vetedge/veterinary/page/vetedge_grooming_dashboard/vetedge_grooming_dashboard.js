frappe.pages["vetedge-grooming-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "grooming",
			title: __("Grooming Dashboard"),
		});
	});
};
