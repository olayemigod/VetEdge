import VetEdgeHome from './vetedge_home/VetEdgeHome.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeHome);

export function mountVetEdgeHome(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	VetEdgeHome.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeHome);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeHome = VetEdgeHome;
	window.mountVetEdgeHome = mountVetEdgeHome;
}

export default VetEdgeHome;
