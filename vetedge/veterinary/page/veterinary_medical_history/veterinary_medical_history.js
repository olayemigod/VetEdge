frappe.pages['veterinary-medical-history'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Medical History'), single_column: true });
	wrapper.page = page;
};

frappe.pages['veterinary-medical-history'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();

	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Veterinary Medical History...'))
		.appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Veterinary Medical History failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			'EdgeAppShell',
			'EdgePageLayout',
			'EdgePageHeader',
			'EdgeFilterBar',
			'EdgeLinkField',
			'EdgeInput',
			'EdgeDataTable',
			'EdgeLoadingState',
			'EdgeErrorState',
			'EdgeEmptyState',
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Veterinary Medical History requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const mountHistory = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			window.VetEdgeRouteAlignment?.installNavigationAdapter?.();
			if (!professional?.installed) {
				showFailure(professional?.message || __('The VetEdge professional shell is unavailable.'));
				return;
			}
			frappe.require('veterinary_medical_history.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVeterinaryMedicalHistory) return;
				try {
					$loading.remove();
					const root = $('<div class="veterinary-medical-history-root" data-edge-product="vetedge"></div>').appendTo(page.body);
					wrapper.vue_app = window.mountVeterinaryMedicalHistory(root[0]);
				} catch (error) {
					console.error('Error mounting Veterinary Medical History:', error);
					showFailure(__('Error mounting Veterinary Medical History: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mountHistory();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountHistory);
	});
};
