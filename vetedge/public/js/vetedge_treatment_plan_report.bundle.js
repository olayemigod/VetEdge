import VetEdgeTreatmentPlanReport from './vetedge_treatment_plan_report/VetEdgeTreatmentPlanReport.vue';

export function mountVetEdgeTreatmentPlanReport(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	VetEdgeTreatmentPlanReport.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeTreatmentPlanReport);
	const view = app.mount(target);
	return { view, refresh: () => view?.load?.(), unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') window.mountVetEdgeTreatmentPlanReport = mountVetEdgeTreatmentPlanReport;
export default VetEdgeTreatmentPlanReport;