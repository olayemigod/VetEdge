function remove_duplicate_revenue_composition_chart(wrapper) {
	$(wrapper).find(".vetedge-revenue-composition-chart-layout").remove();
}

frappe.pages["veterinary-financial-dashboard"].on_page_load = function (wrapper) {
	if (window.vetedgeFinancialDashboard && typeof window.vetedgeFinancialDashboard.mount === "function") {
		return window.vetedgeFinancialDashboard.mount(wrapper);
	}

	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Financial Dashboard"), single_column: true });
	frappe.require("/assets/vetedge/js/dashboard_shell.js", function () {
		window.vetedgeDashboardShell.mount(page, { key: "financial", title: __("Financial Dashboard") });

		// Keep the Revenue Composition cards and remove only the duplicate donut
		// visual. Performance Trends already renders the same component mix chart.
		remove_duplicate_revenue_composition_chart(page.body);
		wrapper.__vetedgeRevenueCompositionObserver?.disconnect?.();
		wrapper.__vetedgeRevenueCompositionObserver = new MutationObserver(() => {
			remove_duplicate_revenue_composition_chart(page.body);
		});
		wrapper.__vetedgeRevenueCompositionObserver.observe(page.body[0], { childList: true, subtree: true });
	});
};

frappe.pages["veterinary-financial-dashboard"].on_page_unload = function (wrapper) {
	wrapper.__vetedgeRevenueCompositionObserver?.disconnect?.();
	wrapper.__vetedgeRevenueCompositionObserver = null;
};
