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
		} catch (error) {
			console.error('Error unmounting Stock Expiry Monitor Vue app:', error);
		}

		wrapper.vue_app = null;
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

			let brandingSettled = false;
			const loadMonitorBundle = () => {
				if (brandingSettled || wrapper.current_visit_id !== visit_id) return;
				brandingSettled = true;
				try {
					window.VetEdgeBrandingUI?.install?.();
				} catch (error) {
					console.warn('VetEdge branding enhancement could not be installed:', error);
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

			if (window.VetEdgeBrandingUI?.install) {
				loadMonitorBundle();
			} else {
				frappe.require('/assets/vetedge/js/vetedge_branding_ui.js?v=20260723-2', loadMonitorBundle);
				window.setTimeout(loadMonitorBundle, 1500);
			}
		};

		if (window.VetEdgeProfessionalUI?.install) {
			loadMonitor();
		} else {
			frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', loadMonitor);
		}
	});
};
