import VetEdgeBillingCenter from './vetedge_billing_center/VetEdgeBillingCenter.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeBillingCenter);

export function mountVetEdgeBillingCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	const Root = {
		...VetEdgeBillingCenter,
		components: { ...runtime.components, ...(VetEdgeBillingCenter.components || {}) },
	};
	const app = runtime.createEdgeApp(Root);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeBillingCenter = VetEdgeBillingCenter;
	window.mountVetEdgeBillingCenter = mountVetEdgeBillingCenter;
}

export default VetEdgeBillingCenter;
