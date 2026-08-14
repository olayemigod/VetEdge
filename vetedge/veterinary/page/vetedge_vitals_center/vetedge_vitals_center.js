frappe.pages['vetedge-vitals-center'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Vital Signs'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-vitals-center'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.refresh) {
		Promise.resolve(wrapper.vue_app.refresh()).catch((error) => console.error('Error refreshing Vital Signs:', error));
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading Vital Signs...')).appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Vital Signs failed to load.')).appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeFilterBar','EdgeLinkField','EdgeInput','EdgeStatCard','EdgeDataTable','EdgeLoadingState','EdgeErrorState','EdgeEmptyState','EdgeModal','EdgeDropdown','EdgeTextarea'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(missing.length ? __('Vital Signs requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The standalone EdgeSuite UI runtime is unavailable.'));
			return;
		}

		const mountVitals = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) {
				showFailure(professional?.message || __('The VetEdge professional shell is unavailable.'));
				return;
			}
			frappe.require('vetedge_edge_modal_presenter.bundle.js', () => {
				frappe.require('vetedge_clinical_record_editor.bundle.js', () => {
					frappe.require('vetedge_vitals_center.bundle.js', () => {
						if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeVitalsCenter) return;
						try {
							$loading.remove();
							const root = $('<div class="vetedge-vitals-center-root" data-edge-product="vetedge"></div>').appendTo(page.body);
							wrapper.vue_app = window.mountVetEdgeVitalsCenter(root[0]);
						} catch (error) {
							console.error('Error mounting Vital Signs:', error);
							showFailure(__('Error mounting Vital Signs: {0}', [error.message || String(error)]));
						}
					});
				});
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mountVitals();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountVitals);
	});
};
