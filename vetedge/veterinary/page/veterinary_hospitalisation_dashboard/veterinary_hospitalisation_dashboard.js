frappe.pages["veterinary-hospitalisation-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Hospitalisation Dashboard"), single_column: true });
	frappe.require("/assets/vetedge/js/dashboard_shell.js", function () {
		window.vetedgeDashboardShell.mount(page, { key: "hospitalisation", title: __("Hospitalisation Dashboard") });
	});
};
