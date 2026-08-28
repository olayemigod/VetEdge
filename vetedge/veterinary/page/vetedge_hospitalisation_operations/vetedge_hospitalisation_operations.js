// Legacy route markers retained for compatibility-source audits only. New navigation
// must not use these destinations directly:
// frappe.set_route('vetedge-hospitalisation-episode', hospitalisation)
// /desk/vetedge-hospitalisation-episode/${encodeURIComponent(hospitalisation)}

function decodeHospitalisationOperationsRoutePart(value) {
	try {
		return decodeURIComponent(String(value || '')).trim();
	} catch (_error) {
		return String(value || '').trim();
	}
}

function hospitalisationOperationsRouteState() {
	const route = window.frappe?.get_route?.() || [];
	const routeName = route?.[0] === 'vetedge-hospitalisation-operations'
		? String(route?.[1] || '').trim()
		: '';

	const pathParts = window.location.pathname.split('/').filter(Boolean);
	const pathName = pathParts[0] === 'desk' && pathParts[1] === 'vetedge-hospitalisation-operations'
		? decodeHospitalisationOperationsRoutePart(pathParts[2])
		: '';

	const params = new URLSearchParams(window.location.search || '');
	const name = String(routeName || pathName || params.get('hospitalisation') || params.get('name') || '').trim();
	return { name, key: name ? `hospitalisation:${name}` : 'operations' };
}

function hospitalisationOperationsDeskUrl(name) {
	const hospitalisation = String(name || '').trim();
	return hospitalisation
		? `/desk/vetedge-hospitalisation-operations/${encodeURIComponent(hospitalisation)}`
		: '/desk/vetedge-hospitalisation-operations';
}

function canonicalizeHospitalisationOperationsRoute(name) {
	const target = hospitalisationOperationsDeskUrl(name);
	if (`${window.location.pathname}${window.location.search}` !== target) {
		window.history.replaceState({}, '', target);
	}
}

function routeToHospitalisationOperations(name = '') {
	const hospitalisation = String(name || '').trim();
	if (window.frappe?.set_route) {
		if (hospitalisation) frappe.set_route('vetedge-hospitalisation-operations', hospitalisation);
		else frappe.set_route('vetedge-hospitalisation-operations');
		return;
	}
	window.location.assign(hospitalisationOperationsDeskUrl(hospitalisation));
}

function openHospitalisationEpisodeRoute(name) {
	const hospitalisation = String(name || '').trim();
	if (!hospitalisation) return;
	routeToHospitalisationOperations(hospitalisation);
}

function hardenHospitalisationOperationsNavigation(wrapper) {
	const view = wrapper.operations_vue_app?.view;
	if (!view) return;

	// Both the main Hospitalisation column and Hospitalisation Exceptions call
	// this shared Vue method. The record opens inside the canonical Operations
	// Page so a stale bundle cannot move the workflow to the retired Episode URL.
	view.openHospitalisationEpisode = openHospitalisationEpisodeRoute;
}

function hardenHostedHospitalisationEpisodeNavigation(wrapper) {
	const view = wrapper.episode_vue_app?.view;
	if (!view) return;

	view.backToOperations = () => routeToHospitalisationOperations();

	if (!view.__vetedgeOperationsHostedEpisodeLoad && typeof view.loadEpisode === 'function') {
		const originalLoadEpisode = view.loadEpisode.bind(view);
		view.loadEpisode = async (name) => {
			const result = await originalLoadEpisode(name);
			canonicalizeHospitalisationOperationsRoute(name);
			return result;
		};
		view.__vetedgeOperationsHostedEpisodeLoad = true;
	}
}

function showHospitalisationWorkspace(wrapper, mode) {
	if (wrapper.operations_root) wrapper.operations_root.hidden = mode !== 'operations';
	if (wrapper.episode_root) wrapper.episode_root.hidden = mode !== 'episode';
	wrapper.hospitalisation_workspace_mode = mode;
	wrapper.vue_app = mode === 'episode' ? wrapper.episode_vue_app : wrapper.operations_vue_app;
	wrapper.page?.set_title?.(mode === 'episode' ? __('Hospitalisation Episode') : __('Hospitalisation Operations'));
}

async function refreshHostedHospitalisationEpisode(wrapper, requested) {
	const view = wrapper.episode_vue_app?.view;
	if (!view || !requested?.name) return false;

	hardenHostedHospitalisationEpisodeNavigation(wrapper);
	if (wrapper.hospitalisation_episode_route_key !== requested.key || view.episode?.name !== requested.name) {
		await view.loadEpisode?.(requested.name);
	} else if (!view.dirty) {
		await view.refreshEpisode?.();
	}
	wrapper.hospitalisation_episode_route_key = requested.key;
	canonicalizeHospitalisationOperationsRoute(requested.name);
	return true;
}

function mountHospitalisationOperationsWorkspace(wrapper, page, visitId, showFailure) {
	if (wrapper.operations_vue_app?.view) {
		showHospitalisationWorkspace(wrapper, 'operations');
		hardenHospitalisationOperationsNavigation(wrapper);
		wrapper.operations_vue_app.view.syncShellContext?.();
		wrapper.operations_vue_app.view.fetchData?.();
		canonicalizeHospitalisationOperationsRoute('');
		return;
	}

	frappe.require('vetedge_hospitalisation_operations.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeHospitalisationOperations) return;
		try {
			wrapper.operations_root = $('<div class="vetedge-hospitalisation-operations-root" data-edge-product="vetedge"></div>')
				.appendTo(page.body)[0];
			wrapper.operations_vue_app = window.mountVetEdgeHospitalisationOperations(wrapper.operations_root);
			showHospitalisationWorkspace(wrapper, 'operations');
			hardenHospitalisationOperationsNavigation(wrapper);
			canonicalizeHospitalisationOperationsRoute('');
		} catch (error) {
			console.error('Error mounting Hospitalisation Operations:', error);
			showFailure(__('Error mounting Hospitalisation Operations: {0}', [error.message || String(error)]));
		}
	});
}

function mountHospitalisationEpisodeWorkspace(wrapper, page, visitId, requested, showFailure) {
	if (wrapper.episode_vue_app?.view) {
		showHospitalisationWorkspace(wrapper, 'episode');
		Promise.resolve(refreshHostedHospitalisationEpisode(wrapper, requested)).catch((error) => {
			console.error('Error refreshing Hospitalisation Episode:', error);
		});
		return;
	}

	frappe.require('vetedge_hospitalisation_episode.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeHospitalisationEpisode) return;
		try {
			wrapper.episode_root = $('<div class="vetedge-hospitalisation-episode-root" data-edge-product="vetedge"></div>')
				.appendTo(page.body)[0];
			wrapper.episode_vue_app = window.mountVetEdgeHospitalisationEpisode(wrapper.episode_root);
			showHospitalisationWorkspace(wrapper, 'episode');
			hardenHostedHospitalisationEpisodeNavigation(wrapper);
			Promise.resolve(refreshHostedHospitalisationEpisode(wrapper, requested)).catch((error) => {
				console.error('Error loading Hospitalisation Episode:', error);
				showFailure(__('Hospitalisation Episode failed to load: {0}', [error.message || String(error)]));
			});
		} catch (error) {
			console.error('Error mounting Hospitalisation Episode:', error);
			showFailure(__('Error mounting Hospitalisation Episode: {0}', [error.message || String(error)]));
		}
	});
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
	const requested = hospitalisationOperationsRouteState();
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	const existing = requested.name ? wrapper.episode_vue_app?.view : wrapper.operations_vue_app?.view;
	if (existing) {
		if (requested.name) {
			showHospitalisationWorkspace(wrapper, 'episode');
			Promise.resolve(refreshHostedHospitalisationEpisode(wrapper, requested)).catch((error) => {
				console.error('Error refreshing mounted Hospitalisation Episode:', error);
			});
		} else {
			showHospitalisationWorkspace(wrapper, 'operations');
			hardenHospitalisationOperationsNavigation(wrapper);
			wrapper.operations_vue_app.view.syncShellContext?.();
			wrapper.operations_vue_app.view.fetchData?.();
			canonicalizeHospitalisationOperationsRoute('');
		}
		return;
	}

	const loadingText = requested.name ? __('Loading Hospitalisation Episode...') : __('Loading Hospitalisation Operations...');
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(loadingText)
		.appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Hospitalisation workspace failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = requested.name
			? ['EdgeAppShell', 'EdgePageLayout', 'EdgePageHeader', 'EdgeStatusBadge', 'EdgeLinkField', 'EdgeDropdown', 'EdgeInput', 'EdgeTextarea', 'EdgeModal', 'EdgeLoadingState', 'EdgeErrorState']
			: ['EdgeAppShell', 'EdgeReportShell', 'EdgeLinkField', 'EdgeDropdown', 'EdgeInput'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Hospitalisation requires the current EdgeSuite UI. Missing: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			$loading.remove();
			window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			window.VetEdgeNavigationRecovery?.install?.();
			if (requested.name) mountHospitalisationEpisodeWorkspace(wrapper, page, visitId, requested, showFailure);
			else mountHospitalisationOperationsWorkspace(wrapper, page, visitId, showFailure);
		};

		if (window.VetEdgeProfessionalUI?.install) mountWorkspace();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
