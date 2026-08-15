import VetEdgeAppointmentFlow from './vetedge_resource_center/VetEdgeAppointmentFlow.vue';
import VetEdgeResourceCenter from './vetedge_resource_center/VetEdgeResourceCenter.vue';
import VetEdgeResourceQuickEditor from './vetedge_resource_center/VetEdgeResourceQuickEditor.vue';

const RESOURCE_ROUTE_KEYS = Object.freeze([
	'resource',
	'search',
	'name',
	'new',
	'branch',
	'status',
	'registration_status',
	'species',
	'patient',
	'service_branch',
	'from_date',
	'to_date',
	'vaccine',
	'lab_test',
]);

const CLINICAL_RESOURCES = new Set(['lab-orders', 'vaccinations']);

function getRequestedRouteParams() {
	const params = new URLSearchParams(window.location.search || '');
	const routeOptions = window.frappe?.route_options || {};
	const consumed = [];

	for (const key of RESOURCE_ROUTE_KEYS) {
		const value = routeOptions[key];
		if (value === undefined || value === null || String(value) === '') continue;
		if (!params.has(key)) params.set(key, String(value));
		consumed.push(key);
	}

	if (consumed.length && window.location.pathname === '/desk/vetedge-resource-center') {
		const query = params.toString();
		const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`;
		window.history.replaceState(window.history.state, '', nextUrl);
		for (const key of consumed) delete routeOptions[key];
	}

	return params;
}

function valueFrom(params, key, fallback = '') {
	return String(params.get(key) ?? fallback ?? '').trim();
}

export function mountVetEdgeResourceCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	if (!runtime.components?.EdgeLinkField || !runtime.components?.EdgeModal || !runtime.components?.EdgeDropdown) {
		throw new Error('VetEdge Resource Center requires the EdgeSuite UI 0.6.2 form runtime.');
	}

	const requestedRoute = getRequestedRouteParams();
	const requestedName = valueFrom(requestedRoute, 'name');
	const requestedNew = requestedRoute.get('new') === '1';

	const flowHost = document.createElement('div');
	flowHost.className = 'vetedge-appointment-flow-host';
	document.body.appendChild(flowHost);

	const quickEditorHost = document.createElement('div');
	quickEditorHost.className = 'vetedge-resource-quick-editor-host';
	document.body.appendChild(quickEditorHost);

	let resourceView = null;
	let lastRefreshAt = Date.now();

	const flowApp = runtime.createEdgeApp(VetEdgeAppointmentFlow, {
		onCreated: async () => {
			await resourceView?.loadPage?.();
			lastRefreshAt = Date.now();
		},
	});
	const flowView = flowApp.mount(flowHost);

	const quickEditorApp = runtime.createEdgeApp(VetEdgeResourceQuickEditor, {
		onSaved: async () => {
			await resourceView?.loadPage?.();
			lastRefreshAt = Date.now();
		},
	});
	const quickEditorView = quickEditorApp.mount(quickEditorHost);

	const ResourceCenterRoot = {
		...VetEdgeResourceCenter,
		components: { ...runtime.components, ...(VetEdgeResourceCenter.components || {}) },
		computed: {
			...(VetEdgeResourceCenter.computed || {}),
			primaryActionLabel() {
				if (!this.page?.can_create) return '';
				if (this.resource === 'appointments') return 'New Appointment';
				if (this.resource === 'lab-orders') return 'New Lab Order';
				if (this.resource === 'vaccinations') return 'New Vaccination';
				return 'Add Record';
			},
		},
		methods: {
			...(VetEdgeResourceCenter.methods || {}),
			openEditor(name = null) {
				if (this.resource === 'appointments' && !name) {
					flowView?.open?.();
					return;
				}
				quickEditorView?.open?.({ resource: this.resource, name });
			},
			openNewConsultation(row) {
				if (!row?.name) return;
				this.openRoute(`/desk/vetedge-clinical-workspace?new=1&patient=${encodeURIComponent(row.name)}`);
			},
		},
	};

	const app = runtime.createEdgeApp(ResourceCenterRoot);
	resourceView = app.mount(target);

	const isAppointments = () => resourceView?.resource === 'appointments';
	const isClinicalResource = () => CLINICAL_RESOURCES.has(resourceView?.resource);

	const getRequestedState = () => {
		const params = getRequestedRouteParams();
		return {
			resource: valueFrom(params, 'resource', 'patients') || 'patients',
			search: valueFrom(params, 'search'),
			name: valueFrom(params, 'name'),
			isNew: params.get('new') === '1',
			branch: valueFrom(params, 'branch'),
			status: valueFrom(params, 'status'),
			registrationStatus: valueFrom(params, 'registration_status'),
			species: valueFrom(params, 'species'),
			patient: valueFrom(params, 'patient'),
			serviceBranch: valueFrom(params, 'service_branch') || valueFrom(params, 'branch'),
			fromDate: valueFrom(params, 'from_date'),
			toDate: valueFrom(params, 'to_date'),
			vaccine: valueFrom(params, 'vaccine'),
			labTest: valueFrom(params, 'lab_test'),
		};
	};

	const setField = (targetState, fieldname, value) => {
		if (!targetState || String(targetState[fieldname] || '') === String(value || '')) return false;
		targetState[fieldname] = value || '';
		return true;
	};

	const setLinkField = (values, labels, fieldname, value) => {
		const changed = setField(values, fieldname, value);
		if (labels && (changed || String(labels[fieldname] || '') !== String(value || ''))) {
			labels[fieldname] = value || '';
		}
		return changed;
	};

	const applyRequestedState = () => {
		if (!resourceView) return { routeChanged: false, state: getRequestedState() };
		const state = getRequestedState();
		let routeChanged = false;
		const allowedResources = resourceView.resourceOptions || [];
		const resourceIsValid = allowedResources.some((option) => option.value === state.resource);
		if (resourceIsValid && resourceView.resource !== state.resource) {
			resourceView.resource = state.resource;
			resourceView.start = 0;
			routeChanged = true;
		}
		if (resourceView.search !== state.search) {
			resourceView.search = state.search;
			resourceView.start = 0;
			routeChanged = true;
		}

		if (state.resource === 'patients') {
			routeChanged = setLinkField(resourceView.patientFilters, resourceView.patientFilterLabels, 'default_branch', state.branch) || routeChanged;
			routeChanged = setField(resourceView.patientFilters, 'status', state.status) || routeChanged;
			routeChanged = setField(resourceView.patientFilters, 'registration_status', state.registrationStatus) || routeChanged;
			routeChanged = setLinkField(resourceView.patientFilters, resourceView.patientFilterLabels, 'species', state.species) || routeChanged;
		} else if (CLINICAL_RESOURCES.has(state.resource)) {
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'patient', state.patient) || routeChanged;
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'service_branch', state.serviceBranch) || routeChanged;
			routeChanged = setField(resourceView.clinicalFilters, 'status', state.status) || routeChanged;
			routeChanged = setField(resourceView.clinicalFilters, 'from_date', state.fromDate) || routeChanged;
			routeChanged = setField(resourceView.clinicalFilters, 'to_date', state.toDate) || routeChanged;
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'vaccine', state.vaccine) || routeChanged;
			routeChanged = setLinkField(resourceView.clinicalFilters, resourceView.clinicalFilterLabels, 'lab_test', state.labTest) || routeChanged;
		}

		if (routeChanged) resourceView.start = 0;
		return { routeChanged, state };
	};

	const openRequestedEditor = (state) => {
		if (!state?.name && !state?.isNew) return;
		if (state.isNew && isAppointments()) {
			flowView?.open?.();
			return;
		}
		if (isClinicalResource()) {
			if (state.isNew) {
				resourceView.openClinicalCreate?.();
				return;
			}
			if (state.name) {
				resourceView.openClinicalRecord?.({ name: state.name });
				return;
			}
		}
		quickEditorView?.open?.({
			resource: resourceView.resource,
			name: state.name || null,
		});
	};

	// `interceptAppointmentAction` is intentionally retired: the Vue component's
	// primaryActionLabel/runPrimaryAction path now owns New Appointment directly.

	// Route alignment captures `name` / `new` before the Resource Center normalizes
	// its list URL so bookmarks, sidebar links and notification deep links can open
	// the canonical EdgeSuite editor rather than falling back to a native Frappe form.
	if (requestedName || requestedNew) {
		window.setTimeout(() => {
			if (!resourceView) return;
			openRequestedEditor({ name: requestedName, isNew: requestedNew });
		}, 0);
	}

	return {
		async refresh(options = {}) {
			if (!resourceView) return false;
			const maxAgeMs = Math.max(Number(options.maxAgeMs || 0), 0);
			const force = options.force === true;
			const { routeChanged, state } = applyRequestedState();
			const hasDeepLink = Boolean(state.name || state.isNew);
			const isFresh = maxAgeMs > 0 && Date.now() - lastRefreshAt < maxAgeMs;

			if (!force && !routeChanged && !hasDeepLink && isFresh) {
				return false;
			}

			await resourceView.loadPage?.();
			lastRefreshAt = Date.now();
			if (hasDeepLink) {
				window.setTimeout(() => openRequestedEditor(state), 0);
			}
			return true;
		},
		unmount() {
			app.unmount();
			flowApp.unmount();
			quickEditorApp.unmount();
			flowHost.remove();
			quickEditorHost.remove();
		},
	};
}

if (typeof window !== 'undefined') {
	window.VetEdgeResourceCenter = VetEdgeResourceCenter;
	window.VetEdgeAppointmentFlow = VetEdgeAppointmentFlow;
	window.VetEdgeResourceQuickEditor = VetEdgeResourceQuickEditor;
	window.mountVetEdgeResourceCenter = mountVetEdgeResourceCenter;
}

export default VetEdgeResourceCenter;