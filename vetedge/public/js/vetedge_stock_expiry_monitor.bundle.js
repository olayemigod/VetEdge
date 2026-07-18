import VetedgeEdgeSuiteShell from './vetedge_shell/VetedgeEdgeSuiteShell.vue';
import VetedgeStockExpiryMonitor from './vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue';

export function mountVetedgeStockExpiryMonitor(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;

	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetedgeStockExpiryMonitor.components = { ...runtime.components, VetedgeEdgeSuiteShell };
	const app = runtime.createEdgeApp(VetedgeStockExpiryMonitor);
	app.mount(target);

	return app;
}

if (typeof window !== 'undefined') {
	window.VetedgeStockExpiryMonitor = VetedgeStockExpiryMonitor;
	window.mountVetedgeStockExpiryMonitor = mountVetedgeStockExpiryMonitor;
}

export default VetedgeStockExpiryMonitor;
