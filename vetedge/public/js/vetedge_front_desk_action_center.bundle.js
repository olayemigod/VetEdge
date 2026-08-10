import VetEdgeFrontDeskActionCenter from './vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const originalCloseActionDialog = VetEdgeFrontDeskActionCenter.methods.closeActionDialog;
VetEdgeFrontDeskActionCenter.methods.closeActionDialog = function closeActionDialog(force = false) {
	if (this.actionBusy && !force) return;
	return originalCloseActionDialog.call(this);
};

const originalExecuteAction = VetEdgeFrontDeskActionCenter.methods.executeAction;
VetEdgeFrontDeskActionCenter.methods.executeAction = async function executeActionWithReliableClose() {
	try { await originalExecuteAction.call(this); }
	finally {
		if (this.actionDialog?.open && !this.actionBusy) this.closeActionDialog(true);
	}
};

applyWorkspaceSafety(VetEdgeFrontDeskActionCenter);

export function mountVetEdgeFrontDeskActionCenter(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	VetEdgeFrontDeskActionCenter.components = runtime.components;
	const app = runtime.createEdgeApp(VetEdgeFrontDeskActionCenter);
	const view = app.mount(target);
	return { view, unmount: () => app.unmount() };
}

if (typeof window !== 'undefined') {
	window.VetEdgeFrontDeskActionCenter = VetEdgeFrontDeskActionCenter;
	window.mountVetEdgeFrontDeskActionCenter = mountVetEdgeFrontDeskActionCenter;
}

export default VetEdgeFrontDeskActionCenter;
