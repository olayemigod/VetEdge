frappe.pages["vetedge-lab-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "lab",
			title: __("Lab Dashboard"),
		});
	});
};
