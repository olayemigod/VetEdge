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

	if (wrapper.vue_app) {
		wrapper.vue_app.unmount();
		wrapper.vue_app = null;
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
					wrapper.vue_app.mount(root[0]);
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
