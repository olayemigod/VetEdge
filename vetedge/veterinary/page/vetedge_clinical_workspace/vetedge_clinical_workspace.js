frappe.pages['vetedge-clinical-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Veterinary Clinical Workspace'),
		single_column: true
	});
	wrapper.page = page;
};

frappe.pages['vetedge-clinical-workspace'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	const resetPageScroll = () => {
		const elements = [
			page.body,
			wrapper,
			...$(wrapper).parents('.layout-main-section-wrapper, .page-body, .desk-page').get()
		].filter(Boolean);
		[...new Set(elements)].forEach((element) => {
			if (typeof element.scrollTo === 'function') element.scrollTo({ top: 0, left: 0 });
			else element.scrollTop = 0;
		});
		if (typeof window.scrollTo === 'function') window.scrollTo(0, 0);
	};

	if (wrapper.vue_app) {
		try {
			wrapper.vue_app.unmount();
		} catch (error) {
			console.warn('Error unmounting Veterinary Clinical Workspace:', error);
		}
		wrapper.vue_app = null;
	}

	$(page.body).empty();
	resetPageScroll();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Veterinary Clinical Workspace...'))
		.appendTo(page.body);

	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Veterinary Clinical Workspace failed to load.'))
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
			'EdgeIcon',
			'EdgeDataTable',
			'EdgeStatusBadge',
			'EdgeLinkField',
			'EdgeModal',
			'EdgeLoadingState',
			'EdgeErrorState'
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		const version = String(runtime?.version || '0.0.0').split('.').map((part) => Number.parseInt(part, 10) || 0);
		const supportsClinical = version[0] > 0 || version[1] >= 5;
		if (!runtime?.createEdgeApp || missing.length || !supportsClinical) {
			showFailure(
				!supportsClinical
					? __('Veterinary Clinical Workspace requires EdgeSuite UI 0.5.0 or newer. Loaded version: {0}', [runtime?.version || __('unknown')])
					: missing.length
						? __('Missing EdgeSuite UI clinical components: {0}', [missing.join(', ')])
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

			frappe.require('vetedge_clinical_workspace.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId) return;
				if (!window.VetEdgeClinicalWorkspace) {
					showFailure(__('The Veterinary Clinical Workspace product bundle is unavailable.'));
					return;
				}
				try {
					$loading.remove();
					const root = $('<div class="vetedge-clinical-workspace-root" data-edge-product="vetedge"></div>')
						.appendTo(page.body);
					wrapper.vue_app = runtime.createEdgeApp(window.VetEdgeClinicalWorkspace);
					wrapper.vue_app.mount(root[0]);
					resetPageScroll();
					window.requestAnimationFrame?.(resetPageScroll);
				} catch (error) {
					console.error('Error mounting Veterinary Clinical Workspace:', error);
					showFailure(__('Error mounting Veterinary Clinical Workspace: {0}', [error.message || String(error)]));
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
