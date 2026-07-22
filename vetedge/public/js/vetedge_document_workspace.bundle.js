import VetEdgeDocumentWorkspace from './vetedge_document_workspace/VetEdgeDocumentWorkspace.vue';

export function mountVetEdgeDocumentWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgeDocumentWorkspace.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeDocumentWorkspace);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeDocumentWorkspace = VetEdgeDocumentWorkspace;
	window.mountVetEdgeDocumentWorkspace = mountVetEdgeDocumentWorkspace;
}

export default VetEdgeDocumentWorkspace;
