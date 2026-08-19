import VetEdgeHospitalisationOperations from './vetedge_hospitalisation_operations/VetEdgeHospitalisationOperations.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeHospitalisationOperations);

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
