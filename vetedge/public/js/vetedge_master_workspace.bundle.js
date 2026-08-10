import VetEdgeMasterWorkspace from './vetedge_master_workspace/VetEdgeMasterWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeMasterWorkspace);

export function mountVetEdgeMasterWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	VetEdgeMasterWorkspace.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeMasterWorkspace);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeMasterWorkspace = VetEdgeMasterWorkspace;
	window.mountVetEdgeMasterWorkspace = mountVetEdgeMasterWorkspace;
}

export default VetEdgeMasterWorkspace;
