function decodeHospitalisationRoutePart(value) {
	try {
		return decodeURIComponent(String(value || '')).trim();
	} catch (_error) {
		return String(value || '').trim();
	}
}

function hospitalisationEpisodeRouteState() {
	const route = window.frappe?.get_route?.() || [];
	const routeName = route?.[0] === 'vetedge-hospitalisation-episode'
		? String(route?.[1] || '').trim()
		: '';

	const pathParts = window.location.pathname.split('/').filter(Boolean);
	const pathName = pathParts[0] === 'desk' && pathParts[1] === 'vetedge-hospitalisation-episode'
		? decodeHospitalisationRoutePart(pathParts[2])
		: '';

	// Query-string and route_options support are retained only for links created
	// by older VetEdge revisions. New drill-throughs use the record path segment.
	const params = new URLSearchParams(window.location.search || '');
	const routeOptionName = String(window.frappe?.route_options?.name || '').trim();
	const name = String(routeName || pathName || params.get('name') || routeOptionName || '').trim();
	return { name, key: name ? `hospitalisation:${name}` : 'missing' };
}

function hospitalisationEpisodeDeskUrl(name) {
	return name
		? `/desk/vetedge-hospitalisation-episode/${encodeURIComponent(name)}`
		: '/desk/vetedge-hospitalisation-episode';
}

function canonicalizeHospitalisationEpisodeRoute(name) {
	const target = hospitalisationEpisodeDeskUrl(name);
	if (`${window.location.pathname}${window.location.search}` !== target) {
		window.history.replaceState({}, '', target);
	}
}

function routeToHospitalisationOperations() {
	if (window.frappe?.set_route) {
		frappe.set_route('vetedge-hospitalisation-operations');
		return;
	}
	window.location.assign('/desk/vetedge-hospitalisation-operations');
}

function hardenMountedHospitalisationEpisodeNavigation(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return;

	// Frappe v16 Desk routing is /desk/... and frappe.set_route owns SPA
	// navigation. Keep the mounted Vue workspace aligned even if a cached bundle
	// still contains an older hard-coded path.
	view.backToOperations = routeToHospitalisationOperations;

	if (!view.__vetedgeCanonicalEpisodeLoad && typeof view.loadEpisode === 'function') {
		const originalLoadEpisode = view.loadEpisode.bind(view);
		view.loadEpisode = async (name) => {
			const result = await originalLoadEpisode(name);
			canonicalizeHospitalisationEpisodeRoute(name);
			return result;
		};
		view.__vetedgeCanonicalEpisodeLoad = true;
	}
}

async function refreshMountedHospitalisationEpisode(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;
	hardenMountedHospitalisationEpisodeNavigation(wrapper);
	const requested = hospitalisationEpisodeRouteState();
	if (!requested.name) {
		view.setRouteError?.(__('Select a Hospitalisation from Hospitalisation Operations.'));
		canonicalizeHospitalisationEpisodeRoute('');
		return true;
	}
	if (wrapper.hospitalisation_episode_route_key !== requested.key || view.episode?.name !== requested.name) {
		await view.loadEpisode?.(requested.name);
	} else {
		await view.refreshEpisode?.();
	}
	wrapper.hospitalisation_episode_route_key = requested.key;
	canonicalizeHospitalisationEpisodeRoute(requested.name);
	return true;
}

frappe.pages['vetedge-hospitalisation-episode'].on_page_load = function(wrapper) {
	wrapper.page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Hospitalisation Episode'),
		single_column: true,
	});
};

frappe.pages['vetedge-hospitalisation-episode'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		Promise.resolve(refreshMountedHospitalisationEpisode(wrapper)).catch((error) => {
			console.error('Error refreshing mounted Hospitalisation Episode:', error);
		});
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Hospitalisation Episode...'))
		.appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Hospitalisation Episode failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			'EdgeAppShell', 'EdgePageLayout', 'EdgePageHeader', 'EdgeStatusBadge',
			'EdgeLinkField', 'EdgeDropdown', 'EdgeInput', 'EdgeTextarea',
			'EdgeModal', 'EdgeLoadingState', 'EdgeErrorState'
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Hospitalisation Episode requires the current EdgeSuite UI. Missing: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			window.VetEdgeNavigationRecovery?.install?.();
			if (professional && !professional.installed) {
				showFailure(professional.message || __('The VetEdge professional shell is unavailable.'));
				return;
			}
			frappe.require('vetedge_hospitalisation_episode.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeHospitalisationEpisode) return;
				try {
					$loading.remove();
					const root = $('<div class="vetedge-hospitalisation-episode-root" data-edge-product="vetedge"></div>')
						.appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeHospitalisationEpisode(root[0]);
					wrapper.hospitalisation_episode_route_key = hospitalisationEpisodeRouteState().key;
					hardenMountedHospitalisationEpisodeNavigation(wrapper);
					Promise.resolve(refreshMountedHospitalisationEpisode(wrapper)).catch((error) => {
						console.error('Error refreshing Hospitalisation Episode after mount:', error);
					});
				} catch (error) {
					console.error('Error mounting Hospitalisation Episode:', error);
					showFailure(__('Error mounting Hospitalisation Episode: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mountWorkspace();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
