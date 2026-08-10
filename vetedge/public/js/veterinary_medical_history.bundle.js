import VeterinaryMedicalHistory from './veterinary_medical_history/VeterinaryMedicalHistory.vue';

export function mountVeterinaryMedicalHistory(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}
	VeterinaryMedicalHistory.components = runtime.components;
	const app = runtime.createEdgeApp(VeterinaryMedicalHistory);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VeterinaryMedicalHistory = VeterinaryMedicalHistory;
	window.mountVeterinaryMedicalHistory = mountVeterinaryMedicalHistory;
}

export default VeterinaryMedicalHistory;
