frappe.pages["veterinary-financial-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "financial",
			title: __("Financial Dashboard"),
		});
	});
};
