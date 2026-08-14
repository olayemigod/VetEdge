frappe.pages['vetedge-treatment-plan-report'].on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __('Planned Treatment'), single_column: true });
};

frappe.pages['vetedge-treatment-plan-report'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	if (wrapper.vue_app?.refresh) {
		Promise.resolve(wrapper.vue_app.refresh()).catch((error) => console.error('Error refreshing Planned Treatment:', error));
		return;
	}
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading Planned Treatment...')).appendTo(page.body);
	const fail = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Planned Treatment failed to load.')).appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell', 'EdgePageLayout', 'EdgePageHeader', 'EdgeFilterBar', 'EdgeLinkField', 'EdgeInput', 'EdgeDropdown', 'EdgeDataTable', 'EdgeStatCard', 'EdgeLoadingState', 'EdgeErrorState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			fail(missing.length ? __('Planned Treatment requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The EdgeSuite UI runtime is unavailable.'));
			return;
		}
		const mount = () => {
			window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			frappe.require('vetedge_treatment_plan_report.bundle.js', () => {
				if (!window.mountVetEdgeTreatmentPlanReport) return fail(__('The Planned Treatment EdgeSuite bundle is unavailable.'));
				try {
					$loading.remove();
					const root = $('<div class="vetedge-treatment-plan-report-root" data-edge-product="vetedge"></div>').appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeTreatmentPlanReport(root[0]);
				} catch (error) {
					fail(__('Error mounting Planned Treatment: {0}', [error.message || String(error)]));
				}
			});
		};
		if (window.VetEdgeProfessionalUI?.install) mount();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mount);
	});
};