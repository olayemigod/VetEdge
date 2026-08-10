frappe.pages['vetedge-master-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Veterinary Masters'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-master-workspace'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading Veterinary masters...')).appendTo(page.body);
	const showFailure = (message) => { $loading.remove(); $('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Veterinary masters failed to load.')).appendTo(page.body); };
	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeFilterBar','EdgeDataTable','EdgeDocumentForm','EdgeWorkflowBar','EdgeLinkField','EdgeDropdown','EdgeInput','EdgeModal','EdgeLoadingState','EdgeEmptyState','EdgeErrorState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) { showFailure(missing.length ? __('Veterinary master pages require EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The standalone EdgeSuite UI runtime is unavailable.')); return; }
		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) { showFailure(professional?.message || __('The VetEdge professional shell is unavailable.')); return; }
			frappe.require('vetedge_master_workspace.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeMasterWorkspace) return;
				try { $loading.remove(); const root = $('<div class="vetedge-master-workspace-root" data-edge-product="vetedge"></div>').appendTo(page.body); wrapper.vue_app = window.mountVetEdgeMasterWorkspace(root[0]); }
				catch (error) { console.error('Error mounting Veterinary Masters:', error); showFailure(__('Error mounting Veterinary Masters: {0}', [error.message || String(error)])); }
			});
		};
		if (window.VetEdgeProfessionalUI?.install) mountWorkspace(); else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
