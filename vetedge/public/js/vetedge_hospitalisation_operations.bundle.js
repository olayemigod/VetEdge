import VetEdgeHospitalisationOperations from './vetedge_hospitalisation_operations/VetEdgeHospitalisationOperations.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeHospitalisationOperations);

function openHospitalisationInOperations(name) {
	const hospitalisation = String(name || '').trim();
	if (!hospitalisation) return;
	if (window.frappe?.set_route) {
		window.frappe.set_route('vetedge-hospitalisation-operations', hospitalisation);
		return;
	}
	window.location.assign(`/desk/vetedge-hospitalisation-operations/${encodeURIComponent(hospitalisation)}`);
}

// Keep the component itself safe even before the Frappe Page wrapper has a
// chance to harden the mounted instance. This removes the old /app/...episode
// destination from active Operations behaviour without duplicating business logic.
if (VetEdgeHospitalisationOperations.methods) {
	VetEdgeHospitalisationOperations.methods.openHospitalisationEpisode = openHospitalisationInOperations;
}

export function mountVetEdgeHospitalisationOperations(target) {
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
