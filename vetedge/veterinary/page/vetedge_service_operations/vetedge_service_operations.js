const VETEDGE_SERVICE_OPERATIONS_REFRESH_MAX_AGE_MS = 15000;
const VETEDGE_SERVICE_OPERATION_RESOURCES = new Set([
	'availability',
	'boarding-bookings',
	'boarding-stays',
	'boarding-care-records',
	'grooming-appointments',
	'grooming-sessions',
]);

function serviceOperationsRouteState() {
	const params = new URLSearchParams(window.location.search || '');
	const requested = params.get('resource') || 'availability';
	const resource = VETEDGE_SERVICE_OPERATION_RESOURCES.has(requested) ? requested : 'availability';
	const search = String(params.get('search') || '').trim();
	const parent = String(params.get('parent') || '').trim();
	const name = String(params.get('name') || '').trim();
	return { resource, search, parent, name, key: `${resource}|${search}|${parent}|${name}` };
}

async function refreshMountedServiceOperations(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;

	const requested = serviceOperationsRouteState();
	const previousKey = wrapper.service_operations_route_key || '';
	const routeChanged = previousKey !== requested.key;
	const stale = Date.now() - Number(wrapper.service_operations_last_refresh_at || 0) >= VETEDGE_SERVICE_OPERATIONS_REFRESH_MAX_AGE_MS;

	if (routeChanged) {
		const resourceChanged = view.resource !== requested.resource;
		view.resource = requested.resource;
		view.search = requested.search;
		view.parent = requested.parent;
		view.requestedName = requested.name;
		if (resourceChanged) {
			view.start = 0;
			view.error = '';
		}
	}

	if (routeChanged || stale) await view.load?.();

	if (!requested.name && view.detail?.open) view.closeDetail?.();

	wrapper.service_operations_route_key = serviceOperationsRouteState().key;
	wrapper.service_operations_last_refresh_at = Date.now();
	return true;
}

frappe.pages['vetedge-service-operations'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Hospital & Services Operations'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-service-operations'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		Promise.resolve(refreshMountedServiceOperations(wrapper)).catch((error) => {
			console.error('Error refreshing mounted Hospital & Services Operations:', error);
		});
		return;
	}

	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();

	const $loading = $('<div class="p-6 text-center text-muted"></div>')
		.text(__('Loading Hospital & Services Operations...'))
		.appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>')
			.text(message || __('Hospital & Services Operations failed to load.'))
			.appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = [
			'EdgeAppShell', 'EdgePageLayout', 'EdgePageHeader', 'EdgeFilterBar',
			'EdgeLinkField', 'EdgeInput', 'EdgeDropdown', 'EdgeTextarea', 'EdgeDataTable',
			'EdgeModal', 'EdgeLoadingState', 'EdgeErrorState',
		];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(
				missing.length
					? __('Hospital & Services Operations requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')])
					: __('The standalone EdgeSuite UI runtime is unavailable.')
			);
			return;
		}

		const mount = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			window.VetEdgeRouteAlignment?.installNavigationAdapter?.();
			window.VetEdgeNavigationRecovery?.install?.();
			if (!professional?.installed) {
				showFailure(professional?.message || __('The VetEdge professional shell is unavailable.'));
				return;
			}
			frappe.require('vetedge_service_operations.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeServiceOperations) return;
				try {
					$loading.remove();
					const root = $('<div class="vetedge-service-operations-root" data-edge-product="vetedge"></div>').appendTo(page.body);
					wrapper.vue_app = window.mountVetEdgeServiceOperations(root[0]);
					wrapper.service_operations_route_key = serviceOperationsRouteState().key;
					wrapper.service_operations_last_refresh_at = Date.now();
				} catch (error) {
					console.error('Error mounting Hospital & Services Operations:', error);
					showFailure(__('Error mounting Hospital & Services Operations: {0}', [error.message || String(error)]));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) mount();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mount);
	});
};
