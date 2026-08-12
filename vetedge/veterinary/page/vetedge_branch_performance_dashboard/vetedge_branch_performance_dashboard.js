frappe.pages["vetedge-branch-performance-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "branch_performance",
			title: __("Branch Performance Dashboard"),
		});
	});
};
