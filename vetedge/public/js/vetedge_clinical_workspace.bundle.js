import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import VetEdgeMedicalHistoryModal from './vetedge_clinical_workspace/VetEdgeMedicalHistoryModal.vue';

export function mountVetEdgeClinicalWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	const historyHost = document.createElement('div');
	historyHost.className = 'vetedge-medical-history-modal-host';
	document.body.appendChild(historyHost);
	VetEdgeMedicalHistoryModal.components = runtime.components;
	const historyApp = runtime.createEdgeApp(VetEdgeMedicalHistoryModal);
	const historyView = historyApp.mount(historyHost);

	const ClinicalWorkspaceRoot = {
		...VetEdgeClinicalWorkspace,
		components: { ...runtime.components, ...(VetEdgeClinicalWorkspace.components || {}) },
		methods: {
			...(VetEdgeClinicalWorkspace.methods || {}),
			openHistory() {
				if (!this.detail?.capabilities?.view_history) return;
				const patient = String(this.form?.patient || '').trim();
				if (!patient) {
					this.error = typeof __ === 'function'
						? __('Select or save a Veterinary Patient before opening Medical History.')
						: 'Select or save a Veterinary Patient before opening Medical History.';
					return;
				}
				historyView?.open?.({
					patient,
					patientLabel: this.form?.patient_name || this.form?.patient_label || patient,
				});
			},
		},
	};
	const app = runtime.createEdgeApp(ClinicalWorkspaceRoot);
	const view = app.mount(target);
	return {
		view,
		unmount() {
			app.unmount();
			historyApp.unmount();
			historyHost.remove();
		},
	};
}

if (typeof window !== 'undefined') {
	window.VetEdgeClinicalWorkspace = VetEdgeClinicalWorkspace;
	window.VetEdgeMedicalHistoryModal = VetEdgeMedicalHistoryModal;
	window.mountVetEdgeClinicalWorkspace = mountVetEdgeClinicalWorkspace;
}

export default VetEdgeClinicalWorkspace;
