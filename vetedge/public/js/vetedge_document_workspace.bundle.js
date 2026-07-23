import VetEdgeDocumentWorkspace from './vetedge_document_workspace/VetEdgeDocumentWorkspace.vue';
import { installWorkspaceRuntime } from './vetedge_document_workspace/workspace_runtime';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeDocumentWorkspace, { guardNavigation: true });
installWorkspaceRuntime(VetEdgeDocumentWorkspace);

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
