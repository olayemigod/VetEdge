console.log('[BOOT] Stock Expiry Monitor controller evaluated');

const appendStockExpiryFailure = function(wrapper, message) {
	const existing = wrapper.querySelector('.vetedge-stock-expiry-load-failure');
	if (existing) existing.remove();

	const failure = document.createElement('div');
	failure.className = 'vetedge-stock-expiry-load-failure alert alert-danger p-6 text-center';
	failure.innerHTML =
		'<strong>' +
		__('Stock Expiry Monitor failed to load') +
		'</strong><div>' +
		frappe.utils.escape_html(message || '') +
		'</div>';
	wrapper.appendChild(failure);
};

try {
	frappe.pages['stock-expiry-monitor'].on_page_load = function(wrapper) {
		console.log('[BOOT] Stock Expiry Monitor on_page_load');
		const page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __('Stock Expiry Monitor'),
			single_column: true
		});

		wrapper.page = page;
	};

	frappe.pages['stock-expiry-monitor'].on_page_show = function(wrapper) {
		const page = wrapper.page;
		if (!page) {
			appendStockExpiryFailure(
				wrapper,
				__('The page shell was not created. Refresh the page and try again.')
			);
			return;
		}

		wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
		const visit_id = wrapper.current_visit_id;

		safeUnmountStockExpiryApp(wrapper);
		$(page.body).empty();

		const $loading = $(
			'<div class="edge-preview-loading-placeholder p-6 text-center text-muted">' +
				__('Loading stock expiry monitor assets...') +
			'</div>'
		).appendTo(page.body);

		const showLoadFailure = function(message) {
			$loading.remove();
			appendStockExpiryFailure(wrapper, message);
		};

		const getEdgeSuiteRuntime = function() {
			return window.EdgeSuiteUI || window.EdgeUI || null;
		};

		const requiredComponents = [
			'EdgeAppShell',
			'EdgePageLayout',
			'EdgePageHeader',
			'EdgeFilterBar',
			'EdgeStatCard',
			'EdgeStatusBadge',
			'EdgeLoadingState',
			'EdgeEmptyState',
			'EdgeErrorState',
			'EdgeNotificationBell',
			'EdgeNotificationDrawer'
		];

		const validateRuntime = function(runtime) {
			if (!runtime) {
				return __('The standalone EdgeSuite UI runtime is unavailable.');
			}

			if (!runtime.createEdgeApp) {
				return __('EdgeSuite UI does not expose createEdgeApp.');
			}

			const components = runtime.components || runtime;
			const missing = requiredComponents.filter((name) => !components[name]);
			if (missing.length) {
				return __('Missing EdgeSuite UI components: {0}', [missing.join(', ')]);
			}

			return null;
		};

		frappe.require('edgeui.bundle.js', () => {
			if (wrapper.current_visit_id !== visit_id) return;

			const runtime = getEdgeSuiteRuntime();
			const runtimeError = validateRuntime(runtime);
			if (runtimeError) {
				showLoadFailure(runtimeError);
				return;
			}

			const loadMonitor = function() {
				if (wrapper.current_visit_id !== visit_id) return;

				const professionalUI = window.VetEdgeProfessionalUI?.install?.();
				if (!professionalUI?.installed) {
					showLoadFailure(
						professionalUI?.message ||
						__('VetEdge requires EdgeSuite UI 0.2 or newer for the professional product shell.')
					);
					return;
				}

				frappe.require('vetedge_stock_expiry_monitor.bundle.js', () => {
					if (wrapper.current_visit_id !== visit_id) return;
					$loading.remove();

					if (!window.VetedgeStockExpiryMonitor) {
						showLoadFailure(__('Failed to load the Stock Expiry Monitor product bundle.'));
						return;
					}

					try {
						const root = $(
							'<div class="vetedge-expiry-monitor-root" data-edge-product="vetedge"></div>'
						).appendTo(page.body);

						wrapper.vue_app = runtime.createEdgeApp(window.VetedgeStockExpiryMonitor);
						wrapper.vue_app.mount(root[0]);
					} catch (error) {
						console.error('Error mounting Stock Expiry Monitor:', error);
						showLoadFailure(
							__('Error mounting Stock Expiry Monitor: {0}', [
								error.message || String(error)
							])
						);
					}
				});
			};

			if (window.VetEdgeProfessionalUI?.install) {
				loadMonitor();
			} else {
				frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', loadMonitor);
			}
		});
	};
} catch (error) {
	console.error('[BOOT] Fatal Stock Expiry Monitor controller error:', error);
}

function safeUnmountStockExpiryApp(wrapper) {
	if (!wrapper.vue_app) return;

	try {
		wrapper.vue_app.unmount();
	} catch (error) {
		console.error('Error unmounting Stock Expiry Monitor Vue app:', error);
	}

	wrapper.vue_app = null;
}
