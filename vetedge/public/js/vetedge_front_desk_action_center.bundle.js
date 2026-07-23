import VetEdgeFrontDeskActionCenter from './vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const originalDetailLinks = VetEdgeFrontDeskActionCenter.computed?.detailLinks;
if (typeof originalDetailLinks === 'function') {
	VetEdgeFrontDeskActionCenter.computed.detailLinks = function detailLinksWithConvertedPatient() {
		const links = originalDetailLinks.call(this) || [];
		const patient = this.detail?.payload?.values?.linked_patient;
		if (patient && !links.some((link) => link.kind === 'patient' && link.name === patient)) {
			links.unshift({ label: 'Open Patient', kind: 'patient', name: patient });
		}
		return links;
	};
}

VetEdgeFrontDeskActionCenter.methods.closeActionDialog = function closeActionDialog(force = false) {
	if (this.actionBusy && !force) return;
	this.actionDialog = { open: false, title: '', subtitle: '', action: null, values: {} };
};

const originalExecuteAction = VetEdgeFrontDeskActionCenter.methods.executeAction;
VetEdgeFrontDeskActionCenter.methods.executeAction = async function executeActionWithReliableClose() {
	const wasBusy = this.actionBusy;
	try {
		await originalExecuteAction.call(this);
	} finally {
		if (!wasBusy && this.actionDialog?.open && !this.actionBusy) {
			this.closeActionDialog(true);
		}
	}
};

applyWorkspaceSafety(VetEdgeFrontDeskActionCenter);

export function mountVetEdgeFrontDeskActionCenter(target) {
	const runtime = window.EdgeSuiteUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	VetEdgeFrontDeskActionCenter.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeFrontDeskActionCenter);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeFrontDeskActionCenter = VetEdgeFrontDeskActionCenter;
	window.mountVetEdgeFrontDeskActionCenter = mountVetEdgeFrontDeskActionCenter;
}

export default VetEdgeFrontDeskActionCenter;
