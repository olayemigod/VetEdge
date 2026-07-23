frappe.pages['vetedge-pricing-master-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Pricing & Service Masters'),
		single_column: true
	});
	wrapper.page = page;
};

frappe.pages['vetedge-pricing-master-workspace'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app) {
		try {
			wrapper.vue_app.unmount();
		} catch (error) {
			console.warn('Error unmounting Pricing Masters Vue app:', error);
		}
		wrapper.vue_app = null;
	}

	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading pricing and service masters...'))
		.appendTo(page.body);

	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Pricing and service masters failed to load.'))
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
			'EdgeDataTable',
			'EdgeDocumentForm',
			'EdgeWorkflowBar',
			'EdgeLinkField',
			'EdgeModal',
			'EdgeLoadingState',
			'EdgeEmptyState',
			'EdgeErrorState'
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		const version = String(runtime?.version || '0.0.0').split('.').map((part) => Number.parseInt(part, 10) || 0);
		const supportsDocuments = version[0] > 0 || version[1] >= 5;
		if (!runtime?.createEdgeApp || missing.length || !supportsDocuments) {
			showFailure(
				!supportsDocuments
					? __('Pricing master pages require EdgeSuite UI 0.5.0 or newer. Loaded version: {0}', [runtime?.version || __('unknown')])
					: missing.length
						? __('Missing EdgeSuite UI pricing master components: {0}', [missing.join(', ')])
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

			frappe.require('vetedge_pricing_master_workspace.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId) return;
				if (!window.VetEdgePricingMasterWorkspace) {
					showFailure(__('The Pricing & Service Masters product bundle is unavailable.'));
					return;
				}
				try {
					$loading.remove();
					const root = $('<div class="vetedge-pricing-master-workspace-root" data-edge-product="vetedge"></div>')
						.appendTo(page.body);
					wrapper.vue_app = runtime.createEdgeApp(window.VetEdgePricingMasterWorkspace);
					wrapper.vue_app.mount(root[0]);
				} catch (error) {
					console.error('Error mounting Pricing & Service Masters:', error);
					showFailure(__('Error mounting Pricing & Service Masters: {0}', [error.message || String(error)]));
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
