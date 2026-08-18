import VetEdgeMasterWorkspace from './vetedge_master_workspace/VetEdgeMasterWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

function installCanonicalDeskLocation(component, path) {
	const methods = component?.methods;
	if (!methods || component.__vetedgeCanonicalDeskLocationInstalled) return component;
	const writeLocation = (method, params = {}) => {
		const url = new URL(window.location.href);
		url.pathname = path;
		url.search = new URLSearchParams(params).toString();
		window.history?.[method]?.(window.history.state, '', `${url.pathname}${url.search}${url.hash}`);
	};
	methods.pushLocation = function (params) { writeLocation('pushState', params); };
	methods.replaceLocation = function (params) { writeLocation('replaceState', params); };
	component.__vetedgeCanonicalDeskLocationInstalled = true;
	return component;
}

installCanonicalDeskLocation(VetEdgeMasterWorkspace, '/desk/vetedge-master-workspace');
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
