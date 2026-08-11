import VetEdgeAppointmentFlow from './vetedge_resource_center/VetEdgeAppointmentFlow.vue';
import VetEdgeResourceCenter from './vetedge_resource_center/VetEdgeResourceCenter.vue';
import VetEdgeResourceQuickEditor from './vetedge_resource_center/VetEdgeResourceQuickEditor.vue';

export function mountVetEdgeResourceCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	if (!runtime.components?.EdgeLinkField || !runtime.components?.EdgeModal || !runtime.components?.EdgeDropdown) {
		throw new Error('VetEdge Resource Center requires the EdgeSuite UI 0.6.2 form runtime.');
	}

	const requestedRoute = new URLSearchParams(window.location.search || '');
	const requestedName = String(requestedRoute.get('name') || '').trim();
	const requestedNew = requestedRoute.get('new') === '1';

	const flowHost = document.createElement('div');
	flowHost.className = 'vetedge-appointment-flow-host';
	document.body.appendChild(flowHost);

	const quickEditorHost = document.createElement('div');
	quickEditorHost.className = 'vetedge-resource-quick-editor-host';
	document.body.appendChild(quickEditorHost);

	let resourceView = null;
	let syncActionLabels = () => {};
	let lastRefreshAt = Date.now();

	const flowApp = runtime.createEdgeApp(VetEdgeAppointmentFlow, {
		onCreated: async () => {
			await resourceView?.loadPage?.();
			lastRefreshAt = Date.now();
			syncActionLabels();
		},
	});
	const flowView = flowApp.mount(flowHost);

	const quickEditorApp = runtime.createEdgeApp(VetEdgeResourceQuickEditor, {
		onSaved: async () => {
			await resourceView?.loadPage?.();
			lastRefreshAt = Date.now();
			syncActionLabels();
		},
	});
	const quickEditorView = quickEditorApp.mount(quickEditorHost);

	const ResourceCenterRoot = {
		...VetEdgeResourceCenter,
		components: { ...runtime.components, ...(VetEdgeResourceCenter.components || {}) },
		methods: {
			...(VetEdgeResourceCenter.methods || {}),
			openEditor(name = null) {
				if (this.resource === 'appointments' && !name) {
					flowView?.open?.();
					return;
				}
				quickEditorView?.open?.({ resource: this.resource, name });
			},
		},
	};

	const app = runtime.createEdgeApp(ResourceCenterRoot);
	resourceView = app.mount(target);

	const isAppointments = () => resourceView?.resource === 'appointments';
	const actionButtonSelector = '.edge-page-header__actions button, .edge-state button';

	syncActionLabels = () => {
		target.querySelectorAll(actionButtonSelector).forEach((button) => {
			const label = String(button.textContent || '').trim();
			if (isAppointments() && label === 'Add Record') {
				button.textContent = 'New Appointment';
				button.setAttribute('data-vetedge-appointment-action', '1');
			} else if (!isAppointments() && label === 'New Appointment') {
				button.textContent = 'Add Record';
				button.removeAttribute('data-vetedge-appointment-action');
			}
		});
	};

	const interceptAppointmentAction = (event) => {
		const button = event.target?.closest?.('button');
		if (!button || !target.contains(button) || !isAppointments()) return;
		const label = String(button.textContent || '').trim();
		if (label !== 'Add Record' && label !== 'New Appointment') return;
		if (button.closest('.vetedge-resource-row-actions')) return;
		event.preventDefault();
		event.stopPropagation();
		event.stopImmediatePropagation?.();
		flowView?.open?.();
	};

	const getRequestedState = () => {
		const params = new URLSearchParams(window.location.search || '');
		return {
			resource: String(params.get('resource') || 'patients').trim() || 'patients',
			search: String(params.get('search') || '').trim(),
			name: String(params.get('name') || '').trim(),
			isNew: params.get('new') === '1',
		};
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
		return { routeChanged, state };
	};

	const openRequestedEditor = (state) => {
		if (!state?.name && !state?.isNew) return;
		if (state.isNew && isAppointments()) {
			flowView?.open?.();
			return;
		}
		quickEditorView?.open?.({
			resource: resourceView.resource,
			name: state.name || null,
		});
	};

	target.addEventListener('click', interceptAppointmentAction, true);
	const observer = new MutationObserver(syncActionLabels);
	observer.observe(target, { childList: true, subtree: true });
	syncActionLabels();

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
			syncActionLabels();
			if (hasDeepLink) {
				window.setTimeout(() => openRequestedEditor(state), 0);
			}
			return true;
		},
		unmount() {
			observer.disconnect();
			target.removeEventListener('click', interceptAppointmentAction, true);
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