frappe.pages["vetedge-executive-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Executive Dashboard"), single_column: true });
	frappe.require("/assets/vetedge/js/dashboard_shell.js", function () {
		window.vetedgeDashboardShell.mount(page, { key: "executive", title: __("Executive Dashboard") });
	});
};
