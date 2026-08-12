frappe.pages["vetedge-vaccination-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "vaccination",
			title: __("Vaccination Dashboard"),
		});
	});
};
