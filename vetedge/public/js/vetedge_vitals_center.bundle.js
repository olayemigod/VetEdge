import VetEdgeVitalsCenter from './vetedge_vitals_center/VetEdgeVitalsCenter.vue';

export function mountVetEdgeVitalsCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	VetEdgeVitalsCenter.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeVitalsCenter);
	const view = app.mount(target);
	return {
		view,
		refresh() {
			return view?.load?.();
		},
		unmount() {
			app.unmount();
		},
	};
}

if (typeof window !== 'undefined') {
	window.VetEdgeVitalsCenter = VetEdgeVitalsCenter;
	window.mountVetEdgeVitalsCenter = mountVetEdgeVitalsCenter;
}

export default VetEdgeVitalsCenter;
