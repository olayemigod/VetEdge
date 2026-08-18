const VETEDGE_MASTER_WORKSPACE_REFRESH_MAX_AGE_MS = 15000;
const VETEDGE_MASTER_WORKSPACE_ROUTE = '/desk/vetedge-master-workspace';
const VETEDGE_MASTER_ROUTE_OPTION_KEYS = ['resource', 'name', 'new', 'search'];

function hydrateMasterWorkspaceRouteFromFrappeOptions() {
	const options = window.frappe?.route_options;
	if (!options || typeof options !== 'object') return false;

	const url = new URL(window.location.href);
	let consumed = false;
	let changed = false;
	for (const key of VETEDGE_MASTER_ROUTE_OPTION_KEYS) {
		const value = options[key];
		if (value === undefined || value === null || String(value) === '') continue;
		consumed = true;
		const text = String(value);
		if (url.searchParams.get(key) !== text) {
			url.searchParams.set(key, text);
			changed = true;
		}
	}
	if (!consumed) return false;

	if (url.pathname !== VETEDGE_MASTER_WORKSPACE_ROUTE) {
		url.pathname = VETEDGE_MASTER_WORKSPACE_ROUTE;
		changed = true;
	}

	const remaining = { ...options };
	for (const key of VETEDGE_MASTER_ROUTE_OPTION_KEYS) delete remaining[key];
	window.frappe.route_options = Object.keys(remaining).length ? remaining : null;

	if (changed && window.history?.replaceState) {
		window.history.replaceState(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
	}
	return changed;
}

function masterWorkspaceRouteKey() {
	return window.location.search || '';
}

async function refreshMountedMasterWorkspace(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;

	const requestedKey = masterWorkspaceRouteKey();
	const routeChanged = (wrapper.master_workspace_route_key || '') !== requestedKey;
	const stale = Date.now() - Number(wrapper.master_workspace_last_refresh_at || 0) >= VETEDGE_MASTER_WORKSPACE_REFRESH_MAX_AGE_MS;
	if (!routeChanged && (!stale || view.dirty)) return true;

	const finishRefresh = async () => {
		await view.loadCurrentRoute?.();
		wrapper.master_workspace_route_key = masterWorkspaceRouteKey();
		wrapper.master_workspace_last_refresh_at = Date.now();
	};

	if (routeChanged && view.dirty && typeof view.confirmDiscard === 'function') {
		view.confirmDiscard(finishRefresh);
		return true;
	}

	await finishRefresh();
	return true;
}

frappe.pages['vetedge-master-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Veterinary Masters'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-master-workspace'].on_page_show = function(wrapper) {
	hydrateMasterWorkspaceRouteFromFrappeOptions();
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		Promise.resolve(refreshMountedMasterWorkspace(wrapper)).catch((error) => {
			console.error('Error refreshing mounted Veterinary Masters:', error);
		});
		return;
	}

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
				try {
					$loading.remove();
					const root = $('<div class="vetedge-master-workspace-root" data-edge-product="vetedge"></div>').appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeMasterWorkspace(root[0]);
					wrapper.master_workspace_route_key = masterWorkspaceRouteKey();
					wrapper.master_workspace_last_refresh_at = Date.now();
				}
				catch (error) { console.error('Error mounting Veterinary Masters:', error); showFailure(__('Error mounting Veterinary Masters: {0}', [error.message || String(error)])); }
			});
		};
		if (window.VetEdgeProfessionalUI?.install) mountWorkspace(); else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
