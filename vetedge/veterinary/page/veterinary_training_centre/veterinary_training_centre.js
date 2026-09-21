frappe.pages['veterinary-training-centre'].on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Veterinary Training Centre'),
		single_column: true,
	});
};

frappe.pages['veterinary-training-centre'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		wrapper.vue_app.view.syncShellContext?.();
		const requested = wrapper.vue_app.view.requestedModuleId?.() || '';
		if (requested && requested !== wrapper.vue_app.view.currentModuleId) {
			wrapper.vue_app.view.openModule?.(requested, { updateUrl: false });
		} else if (!requested && wrapper.vue_app.view.currentModuleId) {
			wrapper.vue_app.view.showList?.();
		}
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Training Centre...'))
		.appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Training Centre failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			'EdgeAppShell',
			'EdgePageLayout',
			'EdgePageHeader',
			'EdgeInput',
			'EdgeLoadingState',
			'EdgeErrorState',
			'EdgeEmptyState',
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Training Centre requires the current EdgeSuite UI. Missing: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const mountTraining = () => {
			if (wrapper.current_visit_id !== visitId) return;
			window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			window.VetEdgeNavigationRecovery?.install?.();
			frappe.require('vetedge_training_centre.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeTrainingCentre) return;
				try {
					$loading.remove();
					const root = $('<div class="vetedge-training-centre-root" data-edge-product="vetedge"></div>')
						.appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeTrainingCentre(root[0]);
				} catch (error) {
					console.error('Error mounting Veterinary Training Centre:', error);
					showFailure(__('Error mounting Training Centre: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mountTraining();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountTraining);
	});
};
