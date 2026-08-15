const VETEDGE_FRONT_DESK_REFRESH_MAX_AGE_MS = 15000;
const VETEDGE_FRONT_DESK_TABS = new Set(['queue', 'guest', 'missed']);

function frontDeskRouteState() {
	const params = new URLSearchParams(window.location.search || '');
	const tab = VETEDGE_FRONT_DESK_TABS.has(params.get('tab')) ? params.get('tab') : 'queue';
	const name = String(params.get('name') || '').trim();
	return { tab, name, key: `${tab}:${name}` };
}

async function refreshMountedFrontDesk(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;

	const requested = frontDeskRouteState();
	const previousKey = wrapper.front_desk_route_key || '';
	const routeChanged = previousKey !== requested.key;
	const stale = Date.now() - Number(wrapper.front_desk_last_refresh_at || 0) >= VETEDGE_FRONT_DESK_REFRESH_MAX_AGE_MS;

	if (view.tab !== requested.tab) {
		view.tab = requested.tab;
		view.filters = { branch: view.filters?.branch || '', practitioner: '', status: '', resolved: '', search: '' };
		if (view.guestList) view.guestList.start = 0;
		if (view.missedList) view.missedList.start = 0;
	}

	if (routeChanged || stale) await view.refreshAll?.();

	if (requested.name) {
		if (requested.tab === 'guest') await view.openGuestDetail?.({ name: requested.name });
		else if (requested.tab === 'missed') await view.openMissedDetail?.({ name: requested.name });
		else await view.openQueueDetail?.({ name: requested.name });
	} else if (view.detail?.open) {
		view.closeDetail?.();
	}

	wrapper.front_desk_route_key = requested.key;
	wrapper.front_desk_last_refresh_at = Date.now();
	return true;
}

frappe.pages['vetedge-front-desk-action-center'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Front Desk Action Centre'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-front-desk-action-center'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		Promise.resolve(refreshMountedFrontDesk(wrapper)).catch((error) => {
			console.error('Error refreshing mounted Front Desk Action Centre:', error);
		});
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading Front Desk Action Centre...')).appendTo(page.body);
	const showFailure = (message) => { $loading.remove(); $('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Front Desk Action Centre failed to load.')).appendTo(page.body); };
	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeFilterBar','EdgeStatCard','EdgeDataTable','EdgeStatusBadge','EdgeLinkField','EdgeDropdown','EdgeInput','EdgeTextarea','EdgeModal','EdgeLoadingState','EdgeErrorState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(missing.length ? __('Front Desk Action Centre requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The standalone EdgeSuite UI runtime is unavailable.'));
			return;
		}
		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) { showFailure(professional?.message || __('The VetEdge professional shell is unavailable.')); return; }
			frappe.require('vetedge_front_desk_action_center.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeFrontDeskActionCenter) return;
				try {
					$loading.remove();
					const root = $('<div class="vetedge-front-desk-action-center-root" data-edge-product="vetedge"></div>').appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeFrontDeskActionCenter(root[0]);
					const requested = frontDeskRouteState();
					wrapper.front_desk_route_key = requested.key;
					wrapper.front_desk_last_refresh_at = Date.now();
					if (requested.name) {
						const opener = requested.tab === 'guest'
							? wrapper.vue_app?.view?.openGuestDetail
							: requested.tab === 'missed'
								? wrapper.vue_app?.view?.openMissedDetail
								: wrapper.vue_app?.view?.openQueueDetail;
						window.setTimeout(() => opener?.call(wrapper.vue_app.view, { name: requested.name }), 0);
					}
				} catch (error) {
					console.error('Error mounting Front Desk Action Centre:', error);
					showFailure(__('Error mounting Front Desk Action Centre: {0}', [error.message || String(error)]));
				}
			});
		};
		if (window.VetEdgeProfessionalUI?.install) mountWorkspace(); else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
