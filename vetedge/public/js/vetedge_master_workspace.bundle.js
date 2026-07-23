import VetEdgeMasterWorkspace from './vetedge_master_workspace/VetEdgeMasterWorkspace.vue';

export function mountVetEdgeMasterWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgeMasterWorkspace.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeMasterWorkspace);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeMasterWorkspace = VetEdgeMasterWorkspace;
	window.mountVetEdgeMasterWorkspace = mountVetEdgeMasterWorkspace;
}

export default VetEdgeMasterWorkspace;
