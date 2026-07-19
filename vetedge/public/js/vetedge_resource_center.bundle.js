import VetEdgeResourceCenter from './vetedge_resource_center/VetEdgeResourceCenter.vue';

export function mountVetEdgeResourceCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgeResourceCenter.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeResourceCenter);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeResourceCenter = VetEdgeResourceCenter;
	window.mountVetEdgeResourceCenter = mountVetEdgeResourceCenter;
}

export default VetEdgeResourceCenter;
