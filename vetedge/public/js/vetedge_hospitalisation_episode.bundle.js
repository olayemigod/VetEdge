import VetEdgeHospitalisationEpisode from './vetedge_hospitalisation_episode/VetEdgeHospitalisationEpisode.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeHospitalisationEpisode);

export function mountVetEdgeHospitalisationEpisode(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	VetEdgeHospitalisationEpisode.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeHospitalisationEpisode);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeHospitalisationEpisode = VetEdgeHospitalisationEpisode;
	window.mountVetEdgeHospitalisationEpisode = mountVetEdgeHospitalisationEpisode;
}

export default VetEdgeHospitalisationEpisode;
