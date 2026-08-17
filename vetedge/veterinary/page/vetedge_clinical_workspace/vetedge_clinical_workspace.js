const VETEDGE_CLINICAL_REFRESH_MAX_AGE_MS = 15000;
const VETEDGE_CLINICAL_MODAL_STYLE_ID = 'vetedge-clinical-modal-edgesuite-style';
const VETEDGE_CLINICAL_ROUTE_REQUEST_EVENT = 'vetedge:clinical-route-request';

function ensureVetEdgeClinicalModalStyles() {
	if (document.getElementById(VETEDGE_CLINICAL_MODAL_STYLE_ID)) return;
	const link = document.createElement('link');
	link.id = VETEDGE_CLINICAL_MODAL_STYLE_ID;
	link.rel = 'stylesheet';
	link.href = '/assets/vetedge/css/vetedge_clinical_modal_edgesuite.css?v=20260814-1';
	document.head.appendChild(link);
}

function clinicalRouteState() {
	const params = new URLSearchParams(window.location.search || '');
	const consultation = String(params.get('consultation') || '').trim();
	const isNew = params.get('new') === '1';
	const patient = String(params.get('patient') || '').trim();
	return {
		consultation,
		isNew,
		patient,
		key: consultation ? `consultation:${consultation}` : isNew ? `new:${patient || '-'}` : 'list',
	};
}

function mountedClinicalStateMatchesRoute(view, requested) {
	if (requested.consultation) {
		return Boolean(view.detail?.open && String(view.detail?.name || '') === requested.consultation);
	}
	if (requested.isNew) {
		if (!view.detail?.open || view.detail?.name) return false;
		if (!requested.patient) return true;
		return String(view.form?.patient || '') === requested.patient;
	}
	return !view.detail?.open;
}

async function openRequestedNewConsultation(view, requested, syncUrl = true) {
	await view.startNewConsultation?.();
	if (requested.patient) await view.selectPatient?.(requested.patient);
	if (!syncUrl) return;

	const patientQuery = requested.patient ? `&patient=${encodeURIComponent(requested.patient)}` : '';
	window.history.replaceState(
		{},
		'',
		`/desk/vetedge-clinical-workspace?new=1${patientQuery}`,
	);
}

function installClinicalRouteRequestListener(wrapper) {
	if (wrapper.__vetedge_clinical_route_request_handler) return;
	const handler = (event) => {
		const detail = event?.detail || {};
		if (detail.type !== 'new') return;
		const patient = String(detail.patient || '').trim();
		const requested = {
			consultation: '',
			isNew: true,
			patient,
			key: `new:${patient || '-'}`,
		};
		wrapper.pending_clinical_route_request = requested;
		const view = wrapper.vue_app?.view;
		if (!view || view.dirty) return;
		Promise.resolve(openRequestedNewConsultation(view, requested, false))
			.then(() => {
				wrapper.clinical_route_key = requested.key;
				wrapper.clinical_last_refresh_at = Date.now();
				wrapper.pending_clinical_route_request = null;
			})
			.catch((error) => console.error('Error applying Veterinary Clinical route request:', error));
	};
	wrapper.__vetedge_clinical_route_request_handler = handler;
	window.addEventListener(VETEDGE_CLINICAL_ROUTE_REQUEST_EVENT, handler);
}

function consumePendingClinicalRouteRequest(wrapper) {
	const requested = wrapper.pending_clinical_route_request;
	const view = wrapper.vue_app?.view;
	if (!requested || !view || view.dirty) return false;
	wrapper.pending_clinical_route_request = null;
	Promise.resolve(openRequestedNewConsultation(view, requested, false))
		.then(() => {
			wrapper.clinical_route_key = requested.key;
			wrapper.clinical_last_refresh_at = Date.now();
		})
		.catch((error) => console.error('Error consuming Veterinary Clinical route request:', error));
	return true;
}

async function refreshMountedClinicalWorkspace(wrapper) {
	const view = wrapper.vue_app?.view;
	if (!view) return false;

	const requested = clinicalRouteState();
	const previousKey = wrapper.clinical_route_key || '';
	const routeChanged = previousKey !== requested.key;
	const stateMismatch = !mountedClinicalStateMatchesRoute(view, requested);
	const needsRouteSync = routeChanged || stateMismatch;
	const stale = Date.now() - Number(wrapper.clinical_last_refresh_at || 0) >= VETEDGE_CLINICAL_REFRESH_MAX_AGE_MS;

	if (view.dirty && needsRouteSync) {
		const confirmed = await view.confirmDiscard?.();
		if (!confirmed) return true;
	}

	if (needsRouteSync) {
		if (requested.consultation) await view.loadDetail?.(requested.consultation);
		else if (requested.isNew) await openRequestedNewConsultation(view, requested);
		else if (view.detail?.open) await view.backToList?.();
		else await view.refreshList?.();
	} else if (stale && !view.dirty) {
		if (view.detail?.open && view.detail?.name) await view.loadDetail?.(view.detail.name);
		else await view.refreshList?.();
	}

	wrapper.clinical_route_key = clinicalRouteState().key;
	wrapper.clinical_last_refresh_at = Date.now();
	return true;
}

frappe.pages['vetedge-clinical-workspace'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Veterinary Clinical Workspace'), single_column: true });
	wrapper.page = page;
	installClinicalRouteRequestListener(wrapper);
};

frappe.pages['vetedge-clinical-workspace'].on_page_show = function(wrapper) {
	ensureVetEdgeClinicalModalStyles();
	installClinicalRouteRequestListener(wrapper);
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;

	if (wrapper.vue_app?.view) {
		if (!consumePendingClinicalRouteRequest(wrapper)) {
			Promise.resolve(refreshMountedClinicalWorkspace(wrapper)).catch((error) => {
				console.error('Error refreshing mounted Veterinary Clinical Workspace:', error);
			});
		}
		return;
	}

	wrapper.clinical_workflow?.destroy?.();
	wrapper.clinical_workflow = null;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading Veterinary Clinical Workspace...')).appendTo(page.body);
	const showFailure = (message) => { $loading.remove(); $('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Veterinary Clinical Workspace failed to load.')).appendTo(page.body); };

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeFilterBar','EdgeStatCard','EdgeDataTable','EdgeStatusBadge','EdgeLinkField','EdgeDropdown','EdgeInput','EdgeTextarea','EdgeModal','EdgeLoadingState','EdgeErrorState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			showFailure(missing.length ? __('Veterinary Clinical Workspace requires EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The standalone EdgeSuite UI runtime is unavailable.'));
			return;
		}
		const mountWorkspace = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			if (!professional?.installed) { showFailure(professional?.message || __('The VetEdge professional shell is unavailable.')); return; }
			frappe.require('vetedge_edge_modal_presenter.bundle.js', () => {
				if (wrapper.current_visit_id !== visitId || !window.VetEdgeEdgeModalPresenter?.ready?.()) {
					showFailure(__('The EdgeSuite clinical modal presenter is unavailable.'));
					return;
				}
				if (!window.vetedgeBillingModal?.open) {
					showFailure(__('The shared VetEdge Billing & Payment modal is unavailable.'));
					return;
				}
				frappe.require('/assets/vetedge/js/vetedge_clinical_resolution_state_guard.js', () => {
					window.installVetEdgeClinicalResolutionStateGuard?.();
					frappe.require('vetedge_clinical_workflow_modal.bundle.js', () => {
						if (wrapper.current_visit_id !== visitId || !window.installVetEdgeClinicalWorkflowModal) {
							showFailure(__('The completed consultation resolution workflow is unavailable.'));
							return;
						}
						frappe.require('vetedge_clinical_workspace.bundle.js', () => {
							if (wrapper.current_visit_id !== visitId || !window.mountVetEdgeClinicalWorkspace) return;
							try {
								$loading.remove();
								const root = $('<div class="vetedge-clinical-workspace-root" data-edge-product="vetedge"></div>').appendTo(page.body);
								wrapper.vue_app = window.mountVetEdgeClinicalWorkspace(root[0]);
								wrapper.clinical_workflow = window.installVetEdgeClinicalWorkflowModal(root[0], wrapper.vue_app?.view);
								wrapper.clinical_route_key = clinicalRouteState().key;
								wrapper.clinical_last_refresh_at = Date.now();
								consumePendingClinicalRouteRequest(wrapper);
							} catch (error) { console.error('Error mounting Veterinary Clinical Workspace:', error); showFailure(__('Error mounting Veterinary Clinical Workspace: {0}', [error.message || String(error)])); }
						});
					});
				});
			});
		};
		if (window.VetEdgeProfessionalUI?.install) mountWorkspace();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountWorkspace);
	});
};
