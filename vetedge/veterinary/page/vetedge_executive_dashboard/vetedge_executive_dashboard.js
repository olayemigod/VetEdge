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

	const resolveAssetUrl = (asset) => frappe.boot?.assets_json?.[asset] || frappe.assets?.bundled_asset?.(asset) || asset;
	const createAssetFailureTrace = (asset) => {
		const url = resolveAssetUrl(asset);
		let error = null;
		const onError = (event) => {
			const filename = String(event.filename || '');
			if (filename && !filename.includes(asset) && !filename.includes(url)) return;
			error = event.error || new Error(event.message || `Failed to execute ${asset}`);
			console.error(`[VetEdge] ${asset} execution failed before loader fallback.`, error, {
				asset: url,
				filename,
				line: event.lineno,
				column: event.colno
			});
		};
		window.addEventListener('error', onError, true);
		return {
			asset: url,
			get error() { return error; },
			stop() { window.removeEventListener('error', onError, true); }
		};
	};

	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Executive Dashboard failed to load.'))
			.appendTo(page.body);
	};

	const requiredComponents = [
		'EdgeAppShell',
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

	const edgeuiTrace = createAssetFailureTrace('edgeui.bundle.js');
	frappe.require('edgeui.bundle.js', () => {
		edgeuiTrace.stop();
		if (wrapper.current_visit_id !== visitId) return;

		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const components = runtime?.components || runtime;
		const missing = requiredComponents.filter((name) => !components?.[name]);

		if (!runtime?.createEdgeApp || missing.length) {
			console.error('[VetEdge] edgeui.bundle.js did not expose the required runtime before loader fallback.', edgeuiTrace.error || new Error('EdgeSuite UI runtime unavailable'), {
				asset: edgeuiTrace.asset,
				missing
			});
			showFailure(
				missing.length
					? __('Missing EdgeSuite UI components: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const dashboardBundleTrace = createAssetFailureTrace('vetedge_executive_dashboard.bundle.js');
		frappe.require('vetedge_executive_dashboard.bundle.js', () => {
			dashboardBundleTrace.stop();
			if (wrapper.current_visit_id !== visitId) return;
			if (!window.VetedgeExecutiveDashboard) {
				console.error('[VetEdge] Executive Dashboard product bundle did not publish its component before loader fallback.', dashboardBundleTrace.error || new Error('Product bundle export unavailable'), {
					asset: dashboardBundleTrace.asset
				});
				showFailure(__('The Executive Dashboard product bundle is unavailable.'));
				return;
			}

			try {
				$loading.remove();
				const root = $('<div class="vetedge-executive-dashboard-root" data-edge-product="vetedge"></div>')
					.appendTo(page.body);
				const dashboard = window.VetedgeExecutiveDashboard;
				// Keep the product bundle and direct page mount on the same component contract.
				dashboard.components = Object.assign({}, runtime.components, dashboard.components || {});
				wrapper.vue_app = runtime.createEdgeApp(dashboard);
				wrapper.vue_app.mount(root[0]);
			} catch (error) {
				console.error('Error mounting Executive Dashboard:', error);
				showFailure(__('Error mounting Executive Dashboard: {0}', [error.message || String(error)]));
			}
		});
	});
};
