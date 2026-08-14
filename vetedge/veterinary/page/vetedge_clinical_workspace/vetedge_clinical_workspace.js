const VETEDGE_CLINICAL_MODAL_STYLE_ID = 'vetedge-clinical-modal-edgesuite-style';

function ensureVetEdgeClinicalModalStyles() {
	if (document.getElementById(VETEDGE_CLINICAL_MODAL_STYLE_ID)) return;
	const link = document.createElement('link');
	link.id = VETEDGE_CLINICAL_MODAL_STYLE_ID;
	link.rel = 'stylesheet';
	link.href = '/assets/vetedge/css/vetedge_clinical_modal_edgesuite.css?v=20260814-1';
	document.head.appendChild(link);
}

frappe.pages['vetedge-clinical-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Veterinary Clinical Workspace'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-clinical-workspace'].on_page_show = function(wrapper) {
	ensureVetEdgeClinicalModalStyles();
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.clinical_workflow?.destroy?.();
	wrapper.clinical_workflow = null;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading Veterinary Clinical Workspace...')).appendTo(page.body);
	const showFailure = (message) => { $loading.remove(); $('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Veterinary Clinical Workspace failed to load.')).appendTo(page.body); };

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeFilterBar','EdgeStatCard','EdgeDataTable','EdgeStatusBadge','EdgeLinkField','EdgeDropdown','EdgeInput','EdgeTextarea','EdgeModal','EdgeLoadingState','EdgeErrorState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(missing.length ? __('Veterinary Clinical Workspace requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The standalone EdgeSuite UI runtime is unavailable.'));
			return;
		}
		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) { showFailure(professional?.message || __('The VetEdge professional shell is unavailable.')); return; }
			frappe.require('vetedge_edge_modal_presenter.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.VetEdgeEdgeModalPresenter?.ready?.()) {
					showFailure(__('The EdgeSuite clinical modal presenter is unavailable.'));
					return;
				}
				frappe.require('/assets/vetedge/js/vetedge_clinical_resolution_state_guard.js', () => {
					window.installVetEdgeClinicalResolutionStateGuard?.();
					frappe.require('vetedge_billing_edgesuite.bundle.js', () => {
						if (wrapper.current_visit_id !== visitId || !window.installVetEdgeBillingEdgeSuite?.()) {
							showFailure(__('The EdgeSuite billing modal is unavailable.'));
							return;
						}
						frappe.require('vetedge_clinical_workflow_modal.bundle.js', () => {
							if (wrapper.current_visit_id !== visitId || !window.installVetEdgeClinicalWorkflowModal) {
								showFailure(__('The completed consultation resolution workflow is unavailable.'));
								return;
							}
							frappe.require('vetedge_clinical_workspace.bundle.js', () => {
								if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeClinicalWorkspace) return;
								try {
									$loading.remove();
									const root = $('<div class="vetedge-clinical-workspace-root" data-edge-product="vetedge"></div>').appendTo(page.body);
									wrapper.vue_app = window.mountVetEdgeClinicalWorkspace(root[0]);
									wrapper.clinical_workflow = window.installVetEdgeClinicalWorkflowModal(root[0], wrapper.vue_app?.view);
								} catch (error) { console.error('Error mounting Veterinary Clinical Workspace:', error); showFailure(__('Error mounting Veterinary Clinical Workspace: {0}', [error.message || String(error)])); }
							});
						});
					});
				});
			});
		};
		if (window.VetEdgeProfessionalUI?.install) mountWorkspace();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
