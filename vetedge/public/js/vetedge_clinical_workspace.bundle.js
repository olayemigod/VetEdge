import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const PROTECTED_EDIT_FIELDS = Object.freeze([
	'item',
	'description',
	'qty',
	'uom',
	'rate',
	'service_type',
	'treatment_type',
	'notes',
]);
const LOCKED_BILLING_STATUSES = new Set(['Submitted Invoiced', 'Paid', 'Cancelled', 'Skipped']);
const LOCKED_PAYMENT_STATUSES = new Set(['Partly Paid', 'Paid', 'Cancelled']);
const SOURCE_CONTROLLED_TYPES = new Set(['Lab Order', 'Vaccination']);

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? {}));
}

function isProtectedTreatmentRow(row = {}) {
	return SOURCE_CONTROLLED_TYPES.has(row.source_type)
		|| LOCKED_BILLING_STATUSES.has(row.billing_status)
		|| LOCKED_PAYMENT_STATUSES.has(row.payment_status);
}

function restoreProtectedTreatmentRows(nextModel, originalModel) {
	const next = clone(nextModel || {});
	const originalRows = clone(originalModel?.planned_treatments || []);
	const nextRows = clone(next.planned_treatments || []);
	let restored = false;

	for (let originalIndex = 0; originalIndex < originalRows.length; originalIndex += 1) {
		const oldRow = originalRows[originalIndex];
		if (!oldRow?.name || !isProtectedTreatmentRow(oldRow)) continue;
		const currentIndex = nextRows.findIndex((row) => row?.name === oldRow.name);
		if (currentIndex < 0) {
			nextRows.splice(Math.min(originalIndex, nextRows.length), 0, oldRow);
			restored = true;
			continue;
		}
		const current = nextRows[currentIndex];
		for (const fieldname of PROTECTED_EDIT_FIELDS) {
			const oldValue = oldRow[fieldname] ?? '';
			const currentValue = current[fieldname] ?? '';
			if (String(oldValue) !== String(currentValue)) {
				current[fieldname] = oldRow[fieldname];
				restored = true;
			}
		}
	}

	next.planned_treatments = nextRows;
	return { model: next, restored };
}

function enhanceClinicalWorkspace(component) {
	const methods = component.methods || {};
	component.methods = methods;

	const originalModelUpdate = methods.onModelUpdate;
	if (typeof originalModelUpdate === 'function') {
		methods.onModelUpdate = function (nextModel) {
			let original = {};
			try {
				original = JSON.parse(this.originalModel || '{}');
			} catch (error) {
				console.warn('Could not read the original clinical model:', error);
			}
			const protectedResult = restoreProtectedTreatmentRows(nextModel, original);
			if (protectedResult.restored) {
				window.frappe?.show_alert?.({
					message: __('Source-controlled or invoiced treatment rows cannot be changed here.'),
					indicator: 'orange',
				});
			}
			return originalModelUpdate.call(this, protectedResult.model);
		};
	}

	const originalClinicalAction = methods.handleConsultationAction;
	if (typeof originalClinicalAction === 'function') {
		methods.handleConsultationAction = function (action) {
			if (!this.dirty || !['history', 'new_vitals'].includes(action?.kind)) {
				return originalClinicalAction.call(this, action);
			}
			return window.frappe?.confirm?.(
				__('Discard unsaved clinical changes before continuing?'),
				() => {
					this.dirty = false;
					return originalClinicalAction.call(this, action);
				},
			);
		};
	}

	for (const methodName of ['openRoute', 'openDoc']) {
		const originalNavigation = methods[methodName];
		if (typeof originalNavigation !== 'function') continue;
		methods[methodName] = function (...args) {
			if (!this.dirty) return originalNavigation.apply(this, args);
			return window.frappe?.confirm?.(
				__('Discard unsaved clinical changes before leaving this record?'),
				() => {
					this.dirty = false;
					return originalNavigation.apply(this, args);
				},
			);
		};
	}

	const originalLoadRoute = methods.loadCurrentRoute;
	if (typeof originalLoadRoute === 'function') {
		methods.loadCurrentRoute = async function (...args) {
			const result = await originalLoadRoute.apply(this, args);
			this.__vetedgeClinicalSafeUrl = window.location.href;
			return result;
		};
	}

	const originalBrowserNavigation = methods.handleBrowserNavigation;
	if (typeof originalBrowserNavigation === 'function') {
		methods.handleBrowserNavigation = function (...args) {
			if (!this.dirty) return originalBrowserNavigation.apply(this, args);
			const targetUrl = window.location.href;
			const safeUrl = this.__vetedgeClinicalSafeUrl || targetUrl;
			window.history.pushState({}, '', safeUrl);
			return window.frappe?.confirm?.(
				__('Discard unsaved clinical changes and open the requested page?'),
				() => {
					this.dirty = false;
					window.history.pushState({}, '', targetUrl);
					return originalBrowserNavigation.apply(this, args);
				},
			);
		};
	}
}

enhanceClinicalWorkspace(VetEdgeClinicalWorkspace);
applyWorkspaceSafety(VetEdgeClinicalWorkspace);

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
