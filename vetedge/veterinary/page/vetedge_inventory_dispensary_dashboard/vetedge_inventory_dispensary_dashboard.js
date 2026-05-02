frappe.pages["vetedge-inventory-dispensary-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Inventory / Dispensary Dashboard"), single_column: true });
	frappe.require("/assets/vetedge/js/dashboard_shell.js", function () {
		window.vetedgeDashboardShell.mount(page, { key: "inventory_dispensary", title: __("Inventory / Dispensary Dashboard") });
	});
};
