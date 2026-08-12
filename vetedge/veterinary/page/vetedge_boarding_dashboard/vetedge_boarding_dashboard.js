frappe.pages["vetedge-boarding-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "boarding",
			title: __("Boarding Dashboard"),
		});
	});
};
