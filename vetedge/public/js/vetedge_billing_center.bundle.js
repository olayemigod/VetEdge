import VetEdgeBillingCenter from './vetedge_billing_center/VetEdgeBillingCenter.vue';
import VetEdgeBillingSessionDetail from './vetedge_billing_center/VetEdgeBillingSessionDetail.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

applyWorkspaceSafety(VetEdgeBillingCenter);
applyWorkspaceSafety(VetEdgeBillingSessionDetail);

const runtimeRoot = (component, methodOverrides = {}) => {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	return {
		runtime,
		Root: {
			...component,
			components: { ...runtime.components, ...(component.components || {}) },
			methods: { ...(component.methods || {}), ...methodOverrides },
		},
	};
};

export function mountVetEdgeBillingCenter(target) {
	const { runtime, Root } = runtimeRoot(VetEdgeBillingCenter, {
		openSession(row) {
			if (!row?.name) return;
			window.location.assign(`/desk/vetedge-billing-sessions?name=${encodeURIComponent(row.name)}`);
		},
	});
	const app = runtime.createEdgeApp(Root);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

export function mountVetEdgeBillingSessionDetail(target) {
	const { runtime, Root } = runtimeRoot(VetEdgeBillingSessionDetail);
	const app = runtime.createEdgeApp(Root);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeBillingCenter = VetEdgeBillingCenter;
	window.VetEdgeBillingSessionDetail = VetEdgeBillingSessionDetail;
	window.mountVetEdgeBillingCenter = mountVetEdgeBillingCenter;
	window.mountVetEdgeBillingSessionDetail = mountVetEdgeBillingSessionDetail;
}

export { VetEdgeBillingSessionDetail };
export default VetEdgeBillingCenter;
