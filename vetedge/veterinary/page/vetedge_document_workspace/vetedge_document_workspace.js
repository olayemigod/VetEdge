frappe.pages['vetedge-document-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Veterinary Documents'),
		single_column: true
	});
	wrapper.page = page;
};

frappe.pages['vetedge-document-workspace'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app) {
		wrapper.vue_app.unmount();
		wrapper.vue_app = null;
	}

	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Veterinary documents...'))
		.appendTo(page.body);

	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Veterinary documents failed to load.'))
			.appendTo(page.body);
	};

	// Use the standalone app's collision-safe bundle name. CoreEdge historically
	// shipped a different `edgeui.bundle.js`, so the generic manifest key is not
	// safe on sites where both apps are installed.
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
			'EdgeSettingsLayout',
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
					? __('VetEdge document pages require EdgeSuite UI 0.5.0 or newer. Loaded version: {0}', [runtime?.version || __('unknown')])
					: missing.length
						? __('Missing EdgeSuite UI document components: {0}', [missing.join(', ')])
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

			const loadWorkspaceBundle = () => {
				if (wrapper.current_visit_id !== visitId) return;
				window.VetEdgeBrandingUI?.install?.();
				frappe.require('vetedge_document_workspace.bundle.js', () => {
					if (wrapper.current_visit_id !== visitId) return;
					if (!window.VetEdgeDocumentWorkspace) {
						showFailure(__('The VetEdge document workspace bundle is unavailable.'));
						return;
					}
					try {
						$loading.remove();
						const root = $('<div class="vetedge-document-workspace-root" data-edge-product="vetedge"></div>')
							.appendTo(page.body);
						wrapper.vue_app = runtime.createEdgeApp(window.VetEdgeDocumentWorkspace);
						wrapper.vue_app.mount(root[0]);
					} catch (error) {
						console.error('Error mounting VetEdge Document Workspace:', error);
						showFailure(__('Error mounting Veterinary documents: {0}', [error.message || String(error)]));
					}
				});
			};

			if (window.VetEdgeBrandingUI?.install) {
				loadWorkspaceBundle();
			} else {
				frappe.require('/assets/vetedge/js/vetedge_branding_ui.js?v=20260723-1', loadWorkspaceBundle);
			}
		};

		if (window.VetEdgeProfessionalUI?.install) {
			mountWorkspace();
		} else {
			frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
		}
	});
};
