import VetEdgeFrontDeskActionCenter from './vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeFrontDeskActionCenter);

export function mountVetEdgeFrontDeskActionCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgeFrontDeskActionCenter.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeFrontDeskActionCenter);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeFrontDeskActionCenter = VetEdgeFrontDeskActionCenter;
	window.mountVetEdgeFrontDeskActionCenter = mountVetEdgeFrontDeskActionCenter;
}

export default VetEdgeFrontDeskActionCenter;
