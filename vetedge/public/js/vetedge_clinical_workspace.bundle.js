import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const originalTreatmentRowLocked = VetEdgeClinicalWorkspace.methods?.treatmentRowLocked;
VetEdgeClinicalWorkspace.methods.treatmentRowLocked = function treatmentRowLockedWithSourceProtection(row) {
	const sourceGenerated = Boolean(
		row?.source_document
		|| row?.source_detail_name
		|| ['Consultation', 'Lab Order', 'Vaccination'].includes(row?.source_type)
	);
	return sourceGenerated || originalTreatmentRowLocked?.call(this, row) === true;
};

const originalSaveVitals = VetEdgeClinicalWorkspace.methods?.saveVitals;
if (typeof originalSaveVitals === 'function') {
	VetEdgeClinicalWorkspace.methods.saveVitals = async function saveVitalsWithReliableClose() {
		const previousVitals = this.detail?.latest_vitals?.name || '';
		await originalSaveVitals.call(this);
		const currentVitals = this.detail?.latest_vitals?.name || '';
		if (!this.busy && currentVitals && currentVitals !== previousVitals) {
			this.vitalsDialog = { open: false, values: {} };
		}
	};
}

applyWorkspaceSafety(VetEdgeClinicalWorkspace, { guardNavigation: true });

export function mountVetEdgeClinicalWorkspace(target) {
	const runtime = window.EdgeSuiteUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgeClinicalWorkspace.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeClinicalWorkspace);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeClinicalWorkspace = VetEdgeClinicalWorkspace;
	window.mountVetEdgeClinicalWorkspace = mountVetEdgeClinicalWorkspace;
}

export default VetEdgeClinicalWorkspace;
