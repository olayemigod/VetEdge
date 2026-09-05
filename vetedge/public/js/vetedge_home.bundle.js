import VetEdgeHome from './vetedge_home/VetEdgeHome.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const APPROVED_DRILLDOWN_ROUTES = Object.freeze({
	'Veterinary Appointment': (name) => `/desk/vetedge-resource-center?resource=appointments&name=${encodeURIComponent(name)}`,
	'Veterinary Consultation': (name) => `/desk/vetedge-clinical-workspace?consultation=${encodeURIComponent(name)}`,
	'Veterinary Lab Order': (name) => `/desk/vetedge-resource-center?resource=lab-orders&name=${encodeURIComponent(name)}`,
	'Veterinary Missed Appointment': (name) => `/desk/vetedge-front-desk-action-center?tab=missed&name=${encodeURIComponent(name)}`,
	'Pet Grooming Appointment': (name) => `/desk/vetedge-service-operations?resource=grooming-appointments&name=${encodeURIComponent(name)}`,
	// Sales Invoice remains an ERPNext accounting document. Open the exact
	// immutable accounting record rather than introducing a duplicate VetEdge editor.
	'Sales Invoice': (name) => `/desk/sales-invoice/${encodeURIComponent(name)}`,
});

function approvedDrilldownRoute(doctype, name) {
	const resolver = APPROVED_DRILLDOWN_ROUTES[String(doctype || '').trim()];
	return resolver && name ? resolver(String(name)) : '';
}

function installApprovedDrilldownNavigation(component) {
	const originalMethods = component.methods || {};
	const originalLoadDrilldown = originalMethods.loadDrilldown;
	return {
		...component,
		methods: {
			...originalMethods,
			async loadDrilldown(start = 0) {
				await originalLoadDrilldown?.call(this, start);
				if (this.drilldown?.doctype === 'Pet Grooming Appointment' && this.drilldown?.metric) {
					this.drilldown.metric = {
						...this.drilldown.metric,
						route: '/desk/vetedge-service-operations?resource=grooming-appointments',
					};
				}
			},
			openDrilldownRecord(row) {
				const name = row?.name;
				const doctype = this.drilldown?.doctype;
				if (!name || !doctype) return;
				const route = approvedDrilldownRoute(doctype, name);
				if (!route) {
					frappe.msgprint(__('This record does not have an approved Veterinary Home drill-through.'));
					return;
				}
				this.openRoute(route);
			},
		},
	};
}

applyWorkspaceSafety(VetEdgeHome);
const VetEdgeHomeRoot = installApprovedDrilldownNavigation(VetEdgeHome);

export function mountVetEdgeHome(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	VetEdgeHomeRoot.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeHomeRoot);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeHome = VetEdgeHomeRoot;
	window.mountVetEdgeHome = mountVetEdgeHome;
}

export { approvedDrilldownRoute };
export default VetEdgeHomeRoot;
