import VetEdgeHospitalisationOperations from './vetedge_hospitalisation_operations/VetEdgeHospitalisationOperations.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeHospitalisationOperations);

const HOSPITALISATION_OPERATIONS_PAGE = 'vetedge-hospitalisation-operations';
const HOSPITALISATION_SAME_PAGE_ROUTER_KEY = '__vetedgeHospitalisationSamePageRouterInstalled';

function hospitalisationOperationsTarget(name = '') {
	const hospitalisation = String(name || '').trim();
	return hospitalisation
		? `/desk/${HOSPITALISATION_OPERATIONS_PAGE}/${encodeURIComponent(hospitalisation)}`
		: `/desk/${HOSPITALISATION_OPERATIONS_PAGE}`;
}

function currentHospitalisationPage() {
	const wrapper = window.frappe?.container?.page;
	return wrapper?.page_name === HOSPITALISATION_OPERATIONS_PAGE && typeof wrapper.on_page_show === 'function'
		? wrapper
		: null;
}

function showHospitalisationInCurrentPage(name = '') {
	const wrapper = currentHospitalisationPage();
	if (!wrapper) return false;

	const hospitalisation = String(name || '').trim();
	const target = hospitalisationOperationsTarget(hospitalisation);
	const current = `${window.location.pathname}${window.location.search || ''}`;

	// Frappe get_route() reads router.current_route. Keep it in sync with the
	// history-only transition so the existing Page loader can distinguish the
	// Operations list from an Episode even after Back to Operations.
	if (window.frappe?.router) {
		window.frappe.router.current_route = hospitalisation
			? [HOSPITALISATION_OPERATIONS_PAGE, hospitalisation]
			: [HOSPITALISATION_OPERATIONS_PAGE];
	}
	if (current !== target) window.history.pushState(window.history.state, '', target);
	wrapper.on_page_show(wrapper);
	return true;
}

function installHospitalisationSamePageRouter() {
	if (!window.frappe?.set_route || window[HOSPITALISATION_SAME_PAGE_ROUTER_KEY]) return;
	const originalSetRoute = window.frappe.set_route;

	window.frappe.set_route = function (...args) {
		const first = String(args?.[0] || '').replace(/^\/+/, '');
		if (first === HOSPITALISATION_OPERATIONS_PAGE) {
			const hospitalisation = String(args?.[1] || '').trim();
			if (showHospitalisationInCurrentPage(hospitalisation)) return Promise.resolve();
		}
		return originalSetRoute.apply(this, args);
	};
	window[HOSPITALISATION_SAME_PAGE_ROUTER_KEY] = true;
}

function openHospitalisationInOperations(name) {
	const hospitalisation = String(name || '').trim();
	if (!hospitalisation) return;
	if (showHospitalisationInCurrentPage(hospitalisation)) return;
	if (window.frappe?.set_route) {
		window.frappe.set_route(HOSPITALISATION_OPERATIONS_PAGE, hospitalisation);
		return;
	}
	window.location.assign(hospitalisationOperationsTarget(hospitalisation));
}

// Keep the component itself safe even before the Frappe Page wrapper has a
// chance to harden the mounted instance. This removes the old /app/...episode
// destination from active Operations behaviour without duplicating business logic.
if (VetEdgeHospitalisationOperations.methods) {
	VetEdgeHospitalisationOperations.methods.openHospitalisationEpisode = openHospitalisationInOperations;
}

export function mountVetEdgeHospitalisationOperations(target) {
	installHospitalisationSamePageRouter();
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	VetEdgeHospitalisationOperations.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeHospitalisationOperations);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeHospitalisationOperations = VetEdgeHospitalisationOperations;
	window.mountVetEdgeHospitalisationOperations = mountVetEdgeHospitalisationOperations;
}

export default VetEdgeHospitalisationOperations;
