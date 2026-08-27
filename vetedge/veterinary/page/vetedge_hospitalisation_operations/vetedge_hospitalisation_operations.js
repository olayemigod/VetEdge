function openHospitalisationEpisodeRoute(name) {
	const hospitalisation = String(name || '').trim();
	if (!hospitalisation) return;

	if (window.frappe?.set_route) {
		frappe.set_route('vetedge-hospitalisation-episode', { name: hospitalisation });
		return;
	}

	window.location.assign(`/desk/vetedge-hospitalisation-episode?name=${encodeURIComponent(hospitalisation)}`);
}

function hardenHospitalisationOperationsNavigation(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return;

	// Both the main Hospitalisation column and Hospitalisation Exceptions call
	// this shared Vue method. Keep the runtime fix in the Frappe Page wrapper so
	// cached product bundles cannot re-introduce the obsolete /app hard route.
	view.openHospitalisationEpisode = openHospitalisationEpisodeRoute;
}

frappe.pages['vetedge-hospitalisation-operations'].on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Hospitalisation Operations'),
		single_column: true,
	});
};

frappe.pages['vetedge-hospitalisation-operations'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		hardenHospitalisationOperationsNavigation(wrapper);
		wrapper.vue_app.view.syncShellContext?.();
		wrapper.vue_app.view.fetchData?.();
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Hospitalisation Operations...'))
		.appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Hospitalisation Operations failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell', 'EdgeReportShell', 'EdgeLinkField', 'EdgeDropdown', 'EdgeInput'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Hospitalisation Operations requires the current EdgeSuite UI. Missing: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			window.VetEdgeNavigationRecovery?.install?.();
			frappe.require('vetedge_hospitalisation_operations.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeHospitalisationOperations) return;
				try {
					$loading.remove();
					const root = $('<div class="vetedge-hospitalisation-operations-root" data-edge-product="vetedge"></div>')
						.appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeHospitalisationOperations(root[0]);
					hardenHospitalisationOperationsNavigation(wrapper);
				} catch (error) {
					console.error('Error mounting Hospitalisation Operations:', error);
					showFailure(__('Error mounting Hospitalisation Operations: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mountWorkspace();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
