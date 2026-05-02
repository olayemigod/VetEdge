frappe.pages["vetedge-grooming-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Grooming Dashboard"), single_column: true });
	frappe.require("/assets/vetedge/js/dashboard_shell.js", function () {
		window.vetedgeDashboardShell.mount(page, { key: "grooming", title: __("Grooming Dashboard") });
	});
};
