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

	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visit_id = wrapper.current_visit_id;

	if (wrapper.vue_app) {
		try {
			wrapper.vue_app.unmount();
		} catch (e) {
			console.error('Error unmounting Stock Expiry Monitor Vue app:', e);
		}
		wrapper.vue_app = null;
	}

	$(page.body).empty();

	const $loading = $('<div class="edge-preview-loading-placeholder p-6 text-center text-muted">' + __('Loading stock expiry monitor assets...') + '</div>')
		.appendTo(page.body);

	const showLoadFailure = function(message) {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"><strong>' + __('Stock Expiry Monitor failed to load') + '</strong><div>' + message + '</div></div>')
			.appendTo(page.body);
	};

	frappe.require('vetedge_stock_expiry_monitor.bundle.js', () => {
		if (wrapper.current_visit_id !== visit_id) return;

		$loading.remove();

		if (!window.VetedgeStockExpiryMonitor || !window.mountVetedgeStockExpiryMonitor) {
			showLoadFailure(__('Failed to load Stock Expiry Monitor bundle.'));
			return;
		}

		try {
			const root = $('<div class="vetedge-expiry-monitor-root" data-edge-product="vetedge"></div>').appendTo(page.body);
			wrapper.vue_app = window.mountVetedgeStockExpiryMonitor(root[0]);
		} catch (e) {
			showLoadFailure(__('Error mounting Stock Expiry Monitor: ') + e.message);
		}
	});
};
