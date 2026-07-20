import VetEdgeHome from './vetedge_home/VetEdgeHome.vue';

export function mountVetEdgeHome(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	const required = [
		'EdgeAppShell',
		'EdgePageLayout',
		'EdgePageHeader',
		'EdgeBranchContextSwitcher',
		'EdgeDashboardLayout',
		'EdgeStatCard',
		'EdgeStatusBadge',
		'EdgeLoadingState',
		'EdgeErrorState',
	];
	const missing = required.filter((name) => !runtime.components?.[name]);
	if (missing.length) {
		throw new Error(`Missing EdgeSuite UI components: ${missing.join(', ')}.`);
	}
	const root = {
		...VetEdgeHome,
		components: { ...runtime.components, ...(VetEdgeHome.components || {}) },
	};
	const app = runtime.createEdgeApp(root);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeHome = VetEdgeHome;
	window.mountVetEdgeHome = mountVetEdgeHome;
}

export default VetEdgeHome;
