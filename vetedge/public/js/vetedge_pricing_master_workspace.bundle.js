import VetEdgePricingMasterWorkspace from './vetedge_pricing_master_workspace/VetEdgePricingMasterWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgePricingMasterWorkspace);

export function mountVetEdgePricingMasterWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgePricingMasterWorkspace.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgePricingMasterWorkspace);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgePricingMasterWorkspace = VetEdgePricingMasterWorkspace;
	window.mountVetEdgePricingMasterWorkspace = mountVetEdgePricingMasterWorkspace;
}

export default VetEdgePricingMasterWorkspace;
