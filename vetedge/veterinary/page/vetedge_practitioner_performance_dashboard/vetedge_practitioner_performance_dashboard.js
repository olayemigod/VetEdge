frappe.pages["vetedge-practitioner-performance-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Practitioner Performance Dashboard"), single_column: true });
	frappe.require("/assets/vetedge/js/dashboard_shell.js", function () {
		window.vetedgeDashboardShell.mount(page, { key: "practitioner_performance", title: __("Practitioner Performance Dashboard") });
	});
};
