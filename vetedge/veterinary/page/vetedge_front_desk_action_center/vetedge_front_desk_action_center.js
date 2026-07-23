frappe.pages['vetedge-front-desk-action-center'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Front Desk Action Centre'),
		single_column: true
	});
	wrapper.page = page;
};

frappe.pages['vetedge-front-desk-action-center'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app) {
		try {
			wrapper.vue_app.unmount();
		} catch (error) {
			console.warn('Error unmounting Front Desk Action Centre:', error);
		}
		wrapper.vue_app = null;
	}

	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Front Desk Action Centre...'))
		.appendTo(page.body);

	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Front Desk Action Centre failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgesuite_ui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI;
		const required = [
			'EdgeAppShell',
			'EdgePageLayout',
			'EdgePageHeader',
			'EdgeFilterBar',
			'EdgeStatCard',
			'EdgeDataTable',
			'EdgeStatusBadge',
			'EdgeLinkField',
			'EdgeModal',
			'EdgeLoadingState',
			'EdgeErrorState'
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		const version = String(runtime?.version || '0.0.0').split('.').map((part) => Number.parseInt(part, 10) || 0);
		const supportsActions = version[0] > 0 || version[1] >= 5;
		if (!runtime?.createEdgeApp || missing.length || !supportsActions) {
			showFailure(
				!supportsActions
					? __('Front Desk Action Centre requires EdgeSuite UI 0.5.0 or newer. Loaded version: {0}', [runtime?.version || __('unknown')])
					: missing.length
						? __('Missing EdgeSuite UI front desk components: {0}', [missing.join(', ')])
						: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) {
				showFailure(professional?.message || __('The VetEdge professional shell is unavailable.'));
				return;
			}

			try {
				window.VetEdgeBrandingUI?.install?.();
			} catch (error) {
				console.warn('VetEdge branding enhancement could not be installed:', error);
			}

			frappe.require('vetedge_front_desk_action_center.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId) return;
				if (!window.VetEdgeFrontDeskActionCenter) {
					showFailure(__('The Front Desk Action Centre product bundle is unavailable.'));
					return;
				}
				try {
					$loading.remove();
					const root = $('<div class="vetedge-front-desk-action-center-root" data-edge-product="vetedge"></div>')
						.appendTo(page.body);
					wrapper.vue_app = runtime.createEdgeApp(window.VetEdgeFrontDeskActionCenter);
					wrapper.vue_app.mount(root[0]);
				} catch (error) {
					console.error('Error mounting Front Desk Action Centre:', error);
					showFailure(__('Error mounting Front Desk Action Centre: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) {
			mountWorkspace();
		} else {
			frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
		}
	});
};
