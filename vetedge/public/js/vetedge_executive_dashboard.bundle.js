import VetedgeEdgeSuiteShell from './vetedge_shell/VetedgeEdgeSuiteShell.vue';
import VetedgeExecutiveDashboard from './vetedge_executive_dashboard/VetedgeExecutiveDashboard.vue';

export function mountVetedgeExecutiveDashboard(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;

	if (!runtime?.createEdgeApp || !runtime?.components) {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetedgeExecutiveDashboard.components = { ...runtime.components, VetedgeEdgeSuiteShell };
	const app = runtime.createEdgeApp(VetedgeExecutiveDashboard);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetedgeExecutiveDashboard = VetedgeExecutiveDashboard;
	window.mountVetedgeExecutiveDashboard = mountVetedgeExecutiveDashboard;
}

export default VetedgeExecutiveDashboard;
