const VETEDGE_EXECUTIVE_REFRESH_MAX_AGE_MS = 15000;

frappe.pages['vetedge-executive-dashboard'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Executive Dashboard'),
		single_column: true
	});

	wrapper.page = page;
};

frappe.pages['vetedge-executive-dashboard'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	// Keep dashboard state and branch metadata in memory when the user navigates
	// elsewhere in Desk and comes back. Only refresh the dashboard payload after
	// the short freshness window; the 500-row branch metadata query remains a
	// cold-mount operation instead of repeating on each visit.
	if (wrapper.vue_app && wrapper.vue_view) {
		const now = Date.now();
		const stale = now - (wrapper.vue_last_refresh_at || 0) >= VETEDGE_EXECUTIVE_REFRESH_MAX_AGE_MS;
		if (stale) {
			try {
				wrapper.vue_view.refresh?.();
				wrapper.vue_last_refresh_at = now;
			} catch (error) {
				console.error('Error refreshing Executive Dashboard:', error);
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
			console.error('Error unmounting Executive Dashboard:', error);
		}
		wrapper.vue_app = null;
		wrapper.vue_view = null;
	}

	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Executive Dashboard assets...'))
		.appendTo(page.body);

	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Executive Dashboard failed to load.'))
			.appendTo(page.body);
	};

	const requiredComponents = [
		'EdgeAppShell',
		'EdgeIcon',
		'EdgePageLayout',
		'EdgePageHeader',
		'EdgeFilterBar',
		'EdgeDashboardLayout',
		'EdgeStatCard',
		'EdgeLoadingState',
		'EdgeEmptyState',
		'EdgeErrorState',
		'EdgeNotificationBell',
		'EdgeNotificationDrawer'
	];

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;

		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const components = runtime?.components || runtime;
		const missing = requiredComponents.filter((name) => !components?.[name]);

		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Missing EdgeSuite UI components: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const loadDashboard = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professionalUI = window.VetEdgeProfessionalUI?.install?.();
			if (!professionalUI?.installed) {
				showFailure(
					professionalUI?.message ||
					__('VetEdge requires EdgeSuite UI 0.2 or newer for the professional product shell.')
				);
				return;
			}

			frappe.require('vetedge_executive_dashboard.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId) return;
				if (!window.VetedgeExecutiveDashboard) {
					showFailure(__('The Executive Dashboard product bundle is unavailable.'));
					return;
				}

				try {
					$loading.remove();
					const root = $('<div class="vetedge-executive-dashboard-root" data-edge-product="vetedge"></div>')
						.appendTo(page.body);
					wrapper.vue_app = runtime.createEdgeApp(window.VetedgeExecutiveDashboard);
					wrapper.vue_view = wrapper.vue_app.mount(root[0]);
					wrapper.vue_last_refresh_at = Date.now();
				} catch (error) {
					console.error('Error mounting Executive Dashboard:', error);
					showFailure(__('Error mounting Executive Dashboard: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) {
			loadDashboard();
		} else {
			frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', loadDashboard);
		}
	});
};
