frappe.pages["veterinary-financial-dashboard"].on_page_load = function (wrapper) {
	if (window.vetedgeFinancialDashboard && typeof window.vetedgeFinancialDashboard.mount === "function") {
		return window.vetedgeFinancialDashboard.mount(wrapper);
	}

	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Financial Dashboard"), single_column: true });
	frappe.require("/assets/vetedge/js/dashboard_shell.js", function () {
		window.vetedgeDashboardShell.mount(page, { key: "financial", title: __("Financial Dashboard") });
		// Performance Trends already contains the service-income composition chart.
		// Remove the older duplicate Revenue Composition section from this page only.
		$(page.body).find(".vetedge-dashboard-composition-section").remove();
	});
};
