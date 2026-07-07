frappe.pages['stock-expiry-monitor'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Stock Expiry Monitor'),
		single_column: true
	});
	wrapper.page = page;
};

frappe.pages['stock-expiry-monitor'].on_page_show = function(wrapper) {
	const page = wrapper.page;

	// Track visit IDs offensively to ignore stale callbacks on navigate away
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visit_id = wrapper.current_visit_id;

	// Cleanly unmount old vue instance
	if (wrapper.vue_app) {
		try {
			wrapper.vue_app.unmount();
		} catch (e) {
			console.error("Error unmounting Stock Expiry Monitor Vue app:", e);
		}
		wrapper.vue_app = null;
	}

	$(page.body).empty();

	// Show loading placeholder
	const $loading = $('<div class="edge-preview-loading-placeholder p-6 text-center text-muted">' + __('Loading design system & stock expiry monitor assets...') + '</div>')
		.appendTo(page.body);

	// 1. Lazy load CoreEdge EdgeUI CSS first
	frappe.require('edgeui.bundle.css', () => {
		if (wrapper.current_visit_id !== visit_id) return;

		// 2. Lazy load CoreEdge EdgeUI JS second
		frappe.require('edgeui.bundle.js', () => {
			if (wrapper.current_visit_id !== visit_id) return;

			if (!window.EdgeUI || !window.EdgeUI.createEdgeApp) {
				$loading.remove();
				$('<div class="alert alert-danger p-6 text-center">' + __('Failed to load EdgeSuite UI shared bundle or createEdgeApp helper.') + '</div>')
					.appendTo(page.body);
				return;
			}

			// 3. Lazy load VetEdge monitor CSS third
			frappe.require('vetedge_stock_expiry_monitor.bundle.css', () => {
				if (wrapper.current_visit_id !== visit_id) return;

				// 4. Lazy load VetEdge monitor JS fourth
				frappe.require('vetedge_stock_expiry_monitor.bundle.js', () => {
					if (wrapper.current_visit_id !== visit_id) return;

					$loading.remove();

					if (!window.VetedgeStockExpiryMonitor) {
						$('<div class="alert alert-danger p-6 text-center">' + __('Failed to load Stock Expiry Monitor bundle.') + '</div>')
							.appendTo(page.body);
						return;
					}

					try {
						const { createEdgeApp } = window.EdgeUI;
						const DashboardComponent = window.VetedgeStockExpiryMonitor;

						// Create mount container
						const root = $('<div class="vetedge-expiry-monitor-root"></div>').appendTo(page.body);

						// Bootstrap Vue app using CoreEdge helper
						wrapper.vue_app = createEdgeApp(DashboardComponent, root[0]);
					} catch (e) {
						$('<div class="alert alert-danger p-6 text-center">' + __('Error mounting Stock Expiry Monitor: ') + e.message + '</div>')
							.appendTo(page.body);
					}
				});
			});
		});
	});
};
