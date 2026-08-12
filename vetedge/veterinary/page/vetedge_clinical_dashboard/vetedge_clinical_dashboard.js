frappe.pages["vetedge-clinical-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "clinical",
			title: __("Clinical Dashboard"),
		});
	});
};
