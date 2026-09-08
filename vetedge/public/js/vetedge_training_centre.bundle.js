import VetEdgeTrainingCentre from './vetedge_training_centre/VetEdgeTrainingCentre.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeTrainingCentre);

export function mountVetEdgeTrainingCentre(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	VetEdgeTrainingCentre.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeTrainingCentre);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeTrainingCentre = VetEdgeTrainingCentre;
	window.mountVetEdgeTrainingCentre = mountVetEdgeTrainingCentre;
}

export default VetEdgeTrainingCentre;
