import VetEdgeFrontDeskActionCenter from './vetedge_front_desk_action_center/VetEdgeFrontDeskActionCenter.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const SMART_APPOINTMENT_API = Object.freeze({
	state: 'vetedge.services.appointment_actions.get_appointment_action_state',
	perform: 'vetedge.services.appointment_actions.perform_appointment_action',
});

async function loadSmartAppointmentState(view) {
	const payload = view.detail?.payload;
	if (view.detail?.type !== 'queue' || !payload?.name) return null;
	const response = await frappe.call(SMART_APPOINTMENT_API.state, { appointment: payload.name });
	const state = response?.message || {};
	payload.actions = state.actions || [];
	payload.smart_state = state;
	return state;
}

const originalCloseActionDialog = VetEdgeFrontDeskActionCenter.methods.closeActionDialog;
VetEdgeFrontDeskActionCenter.methods.closeActionDialog = function closeActionDialog(force = false) {
	if (this.actionBusy && !force) return;
	return originalCloseActionDialog.call(this);
};

const originalOpenQueueDetail = VetEdgeFrontDeskActionCenter.methods.openQueueDetail;
VetEdgeFrontDeskActionCenter.methods.openQueueDetail = async function openQueueDetailWithSmartActions(row) {
	await originalOpenQueueDetail.call(this, row);
	try {
		await loadSmartAppointmentState(this);
	} catch (error) {
		this.error = error?.message || __('Appointment actions could not be loaded.');
	}
};

const originalPrepareAction = VetEdgeFrontDeskActionCenter.methods.prepareAction;
VetEdgeFrontDeskActionCenter.methods.prepareAction = function prepareSmartAction(action) {
	if (this.detail?.type === 'queue' && action?.navigation) {
		this.actionDialog = {
			open: false,
			action,
			title: action.label,
			subtitle: this.detailTitle,
			values: {},
		};
		return this.executeAction();
	}
	return originalPrepareAction.call(this, action);
};

const originalExecuteAction = VetEdgeFrontDeskActionCenter.methods.executeAction;
VetEdgeFrontDeskActionCenter.methods.executeAction = async function executeActionWithSmartAppointmentRouting() {
	if (this.detail?.type !== 'queue') {
		try { await originalExecuteAction.call(this); }
		finally {
			if (this.actionDialog?.open && !this.actionBusy) this.closeActionDialog(true);
		}
		return;
	}

	const action = this.actionDialog?.action;
	const appointment = this.detail?.payload?.name;
	if (!action?.key || !appointment || this.actionBusy) return;

	let targetRoute = '';
	this.actionBusy = true;
	try {
		const response = await frappe.call(SMART_APPOINTMENT_API.perform, {
			appointment,
			action: action.key,
			expected_modified: this.detail.payload.modified,
		});
		const result = response?.message || {};
		if (result.message) {
			frappe.show_alert({ message: __(result.message), indicator: 'green' });
		}
		targetRoute = result.open?.route || '';
		await this.refreshAll();
		if (!targetRoute) {
			await originalOpenQueueDetail.call(this, { name: appointment });
			await loadSmartAppointmentState(this);
		}
	} catch (error) {
		this.error = error?.message || __('Appointment action could not be completed.');
	} finally {
		this.actionBusy = false;
		if (this.actionDialog?.open) this.closeActionDialog(true);
	}

	if (targetRoute) {
		this.closeDetail();
		this.openRoute(targetRoute);
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
