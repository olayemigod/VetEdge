frappe.pages["vetedge-inventory-dispensary-dashboard"].on_page_load = function (wrapper) {
	frappe.require("vetedge_dashboard_host.bundle.js", function () {
		window.mountVetEdgeDashboardHost(wrapper, {
			key: "inventory_dispensary",
			title: __("Inventory / Dispensary Dashboard"),
		});
	});
};
