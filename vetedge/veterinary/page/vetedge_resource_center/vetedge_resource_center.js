frappe.pages['vetedge-resource-center'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Veterinary Resource Center'),
		single_column: true
	});
	wrapper.page = page;
};

frappe.pages['vetedge-resource-center'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app) {
		wrapper.vue_app.unmount();
		wrapper.vue_app = null;
	}

	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Veterinary Resource Center...'))
		.appendTo(page.body);

	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Veterinary Resource Center failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			'EdgeAppShell',
			'EdgeIcon',
			'EdgePageLayout',
			'EdgePageHeader',
			'EdgeFilterBar',
			'EdgeLoadingState',
			'EdgeEmptyState',
			'EdgeErrorState'
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Missing EdgeSuite UI components: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const loadResourceCenter = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) {
				showFailure(
					professional?.message ||
					__('VetEdge requires EdgeSuite UI 0.2 or newer for the professional product shell.')
				);
				return;
			}

			let brandingSettled = false;
			const loadResourceBundle = () => {
				if (brandingSettled || wrapper.current_visit_id !== visitId) return;
				brandingSettled = true;
				try {
					window.VetEdgeBrandingUI?.install?.();
				} catch (error) {
					console.warn('VetEdge branding enhancement could not be installed:', error);
				}
				frappe.require('vetedge_resource_center.bundle.js', () => {
					if (wrapper.current_visit_id !== visitId) return;
					if (!window.VetEdgeResourceCenter) {
						showFailure(__('The Veterinary Resource Center product bundle is unavailable.'));
						return;
					}

					try {
						$loading.remove();
						const root = $('<div class="vetedge-resource-center-root" data-edge-product="vetedge"></div>')
							.appendTo(page.body);
						wrapper.vue_app = runtime.createEdgeApp(window.VetEdgeResourceCenter);
						wrapper.vue_app.mount(root[0]);
					} catch (error) {
						console.error('Error mounting Veterinary Resource Center:', error);
						showFailure(__('Error mounting Veterinary Resource Center: {0}', [error.message || String(error)]));
					}
				});
			};

			if (window.VetEdgeBrandingUI?.install) {
				loadResourceBundle();
			} else {
				frappe.require('/assets/vetedge/js/vetedge_branding_ui.js?v=20260723-2', loadResourceBundle);
				window.setTimeout(loadResourceBundle, 1500);
			}
		};

		if (window.VetEdgeProfessionalUI?.install) {
			loadResourceCenter();
		} else {
			frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', loadResourceCenter);
		}
	});
};
