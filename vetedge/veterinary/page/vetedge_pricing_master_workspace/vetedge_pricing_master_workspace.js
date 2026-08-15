const VETEDGE_PRICING_WORKSPACE_REFRESH_MAX_AGE_MS = 15000;

function pricingWorkspaceRouteKey() {
	return window.location.search || '';
}

async function refreshMountedPricingWorkspace(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;

	const requestedKey = pricingWorkspaceRouteKey();
	const routeChanged = (wrapper.pricing_workspace_route_key || '') !== requestedKey;
	const stale = Date.now() - Number(wrapper.pricing_workspace_last_refresh_at || 0) >= VETEDGE_PRICING_WORKSPACE_REFRESH_MAX_AGE_MS;
	if (!routeChanged && (!stale || view.dirty)) return true;

	const finishRefresh = async () => {
		await view.loadCurrentRoute?.();
		wrapper.pricing_workspace_route_key = pricingWorkspaceRouteKey();
		wrapper.pricing_workspace_last_refresh_at = Date.now();
	};

	if (routeChanged && view.dirty && typeof view.confirmDiscard === 'function') {
		view.confirmDiscard(finishRefresh);
		return true;
	}

	await finishRefresh();
	return true;
}

frappe.pages['vetedge-pricing-master-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Pricing & Service Masters'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-pricing-master-workspace'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		Promise.resolve(refreshMountedPricingWorkspace(wrapper)).catch((error) => {
			console.error('Error refreshing mounted Pricing & Service Masters:', error);
		});
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading pricing and service masters...')).appendTo(page.body);
	const showFailure = (message) => { $loading.remove(); $('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Pricing and service masters failed to load.')).appendTo(page.body); };
	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeFilterBar','EdgeDataTable','EdgeDocumentForm','EdgeWorkflowBar','EdgeLinkField','EdgeDropdown','EdgeInput','EdgeModal','EdgeLoadingState','EdgeEmptyState','EdgeErrorState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) { showFailure(missing.length ? __('Pricing master pages require EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The standalone EdgeSuite UI runtime is unavailable.')); return; }
		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.(); window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) { showFailure(professional?.message || __('The VetEdge professional shell is unavailable.')); return; }
			frappe.require('vetedge_pricing_master_workspace.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgePricingMasterWorkspace) return;
				try {
					$loading.remove();
					const root = $('<div class="vetedge-pricing-master-workspace-root" data-edge-product="vetedge"></div>').appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgePricingMasterWorkspace(root[0]);
					wrapper.pricing_workspace_route_key = pricingWorkspaceRouteKey();
					wrapper.pricing_workspace_last_refresh_at = Date.now();
				}
				catch (error) { console.error('Error mounting Pricing & Service Masters:', error); showFailure(__('Error mounting Pricing & Service Masters: {0}', [error.message || String(error)])); }
			});
		};
		if (window.VetEdgeProfessionalUI?.install) mountWorkspace(); else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
