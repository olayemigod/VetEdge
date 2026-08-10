import VetEdgeServiceOperations from './vetedge_service_operations/VetEdgeServiceOperations.vue';

export function mountVetEdgeServiceOperations(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	const Root = {
		...VetEdgeServiceOperations,
		components: { ...runtime.components, ...(VetEdgeServiceOperations.components || {}) },
	};
	const app = runtime.createEdgeApp(Root);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeServiceOperations = VetEdgeServiceOperations;
	window.mountVetEdgeServiceOperations = mountVetEdgeServiceOperations;
}

export default VetEdgeServiceOperations;
