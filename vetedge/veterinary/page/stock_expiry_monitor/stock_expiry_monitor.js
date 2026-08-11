const VETEDGE_STOCK_EXPIRY_REFRESH_MAX_AGE_MS = 15000;

function getVetEdgeStockBranchContext() {
	return (
		frappe.boot?.session_defaults?.branch ||
		frappe.boot?.edgesuite_product_menu?.branch ||
		frappe.boot?.user_info?.[frappe.session?.user]?.branch ||
		'All Branches'
	);
}

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

	// Reuse the mounted monitor when returning through Desk navigation. This is
	// especially important because the current cold load resolves warehouse and
	// item-group filter metadata. Reusing the Vue instance prevents those lists
	// from being downloaded again on every page visit.
	if (wrapper.vue_app && wrapper.vue_view) {
		const now = Date.now();
		const branchContext = getVetEdgeStockBranchContext();
		const branchChanged = wrapper.vue_branch_context !== branchContext;
		const stale = now - (wrapper.vue_last_refresh_at || 0) >= VETEDGE_STOCK_EXPIRY_REFRESH_MAX_AGE_MS;

		wrapper.vue_view.syncShellContext?.();
		wrapper.vue_branch_context = branchContext;

		if (branchChanged || stale) {
			try {
				wrapper.vue_view.fetchData?.();
				wrapper.vue_last_refresh_at = now;
			} catch (error) {
				console.error('Error refreshing Stock Expiry Monitor:', error);
			}
		}
		return;
	}

	// Backward-compatible cleanup for an older cached page instance that did not
	// retain the mounted component proxy.
	if (wrapper.vue_app) {
		try {
			wrapper.vue_app.unmount();
		} catch (error) {
			console.error('Error unmounting Stock Expiry Monitor Vue app:', error);
		}

		wrapper.vue_app = null;
		wrapper.vue_view = null;
	}

	$(page.body).empty();

	const $loading = $(
		'<div class="edge-preview-loading-placeholder p-6 text-center text-muted">' +
			__('Loading stock expiry monitor assets...') +
		'</div>'
	).appendTo(page.body);

	const showLoadFailure = function(message) {
		$loading.remove();

		$(
			'<div class="alert alert-danger p-6 text-center">' +
				'<strong>' +
				__('Stock Expiry Monitor failed to load') +
				'</strong>' +
				'<div>' +
				frappe.utils.escape_html(message || '') +
				'</div>' +
			'</div>'
		).appendTo(page.body);
	};

	const getEdgeSuiteRuntime = function() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	};

	const requiredComponents = [
		'EdgeAppShell',
		'EdgeIcon',
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

		if (!runtime?.createEdgeApp) {
			return __('EdgeSuite UI does not expose createEdgeApp.');
		}

		const components = runtime?.components || runtime;
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

		// Keep both runtime globals aligned before the product bundle evaluates.
		// Older VetEdge consumers still resolve components from window.EdgeUI,
		// while the standalone shared runtime is canonical on window.EdgeSuiteUI.
		if (!window.EdgeSuiteUI) window.EdgeSuiteUI = runtime;
		if (!window.EdgeUI) window.EdgeUI = runtime;

		const loadMonitor = () => {
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

					wrapper.vue_app = runtime.createEdgeApp(
						window.VetedgeStockExpiryMonitor
					);

					wrapper.vue_view = wrapper.vue_app.mount(root[0]);
					wrapper.vue_last_refresh_at = Date.now();
					wrapper.vue_branch_context = getVetEdgeStockBranchContext();
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
