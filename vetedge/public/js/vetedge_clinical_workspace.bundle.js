import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const CLINICAL_CONTEXT_API = Object.freeze({
	options: 'vetedge.services.clinical_workspace_context.get_clinical_context_options',
	patientOwner: 'vetedge.services.clinical_workspace_context.get_patient_owner_context',
});
const ELEVATED_ROLES = new Set(['System Manager', 'VetEdge Administrator']);
const blankPatientContext = () => ({ patient: {}, owner: {} });
const currentUser = () => window.frappe?.session?.user || '';
const currentRoles = () => new Set(window.frappe?.user_roles || []);
const restrictedDoctor = () => {
	const roles = currentRoles();
	return roles.has('VetEdge Doctor') && ![...ELEVATED_ROLES].some((role) => roles.has(role));
};
const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message);
const escapeHtml = (value) => {
	if (window.frappe?.utils?.escape_html) return frappe.utils.escape_html(String(value || ''));
	const element = document.createElement('div');
	element.textContent = String(value || '');
	return element.innerHTML;
};

const originalData = VetEdgeClinicalWorkspace.data;
VetEdgeClinicalWorkspace.data = function clinicalWorkspaceDataWithPatientContext() {
	const state = originalData.call(this) || {};
	return { ...state, patientContext: blankPatientContext() };
};

VetEdgeClinicalWorkspace.computed = VetEdgeClinicalWorkspace.computed || {};
VetEdgeClinicalWorkspace.computed.isRestrictedDoctor = restrictedDoctor;
const originalDetailSubtitle = VetEdgeClinicalWorkspace.computed.detailSubtitle;
VetEdgeClinicalWorkspace.computed.detailSubtitle = function clinicalDetailSubtitleWithOwner() {
	const base = originalDetailSubtitle?.call(this) || 'Clinical consultation capture';
	const owner = this.patientContext?.owner || {};
	const ownerSummary = [
		owner.label ? `Owner: ${owner.label}` : '',
		owner.mobile_no ? `Tel: ${owner.mobile_no}` : '',
	].filter(Boolean);
	return [base, ...ownerSummary].filter(Boolean).join(' · ');
};

VetEdgeClinicalWorkspace.methods.showOwnerDetails = function showOwnerDetails() {
	const patient = this.patientContext?.patient || {};
	const owner = this.patientContext?.owner || {};
	if (!owner.name && !owner.label) return;

	const rows = [
		['Owner', owner.label || owner.name],
		['Phone', owner.mobile_no],
		['Email', owner.email_id],
		['Emergency Contact', patient.emergency_contact],
		['Patient Species', patient.species],
		['Patient Breed', patient.breed],
	].filter(([, value]) => value);
	const message = rows.length
		? `<div class="vetedge-owner-details">${rows.map(([label, value]) => `<p><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</p>`).join('')}</div>`
		: '<p>No additional owner details are available.</p>';
	frappe.msgprint({ title: 'Pet Owner Details', message, indicator: 'blue' });
};

VetEdgeClinicalWorkspace.methods.syncOwnerDetailsButton = function syncOwnerDetailsButton() {
	this.$nextTick?.(() => {
		const actions = document.querySelector('.vetedge-clinical-detail .vetedge-clinical-statusbar .vetedge-clinical-actions');
		if (!actions) return;
		let button = actions.querySelector('.vetedge-owner-details-button');
		const owner = this.patientContext?.owner || {};
		if (!owner.name && !owner.label) {
			button?.remove();
			return;
		}
		if (!button) {
			button = document.createElement('button');
			button.type = 'button';
			button.className = 'edge-button vetedge-owner-details-button';
			button.textContent = 'View Owner Details';
			actions.prepend(button);
		}
		button.onclick = () => this.showOwnerDetails();
	});
};

VetEdgeClinicalWorkspace.methods.loadPatientOwnerContext = async function loadPatientOwnerContext(patient, applyDefaultBranch = true) {
	const request = Symbol('patient-context');
	this._patientContextRequest = request;
	if (!patient) {
		this.patientContext = blankPatientContext();
		this.form.primary_owner = '';
		this.form.primary_owner_label = '';
		this.syncOwnerDetailsButton();
		return;
	}
	try {
		const context = await call(CLINICAL_CONTEXT_API.patientOwner, { patient });
		if (this._patientContextRequest !== request || this.form.patient !== patient) return;
		this.patientContext = { ...blankPatientContext(), ...(context || {}) };
		this.form.primary_owner = context?.owner?.name || '';
		this.form.primary_owner_label = context?.owner?.label || '';
		if (applyDefaultBranch && !this.form.service_branch && context?.patient?.default_branch) {
			this.form.service_branch = context.patient.default_branch;
			this.markDirty();
		}
		this.syncOwnerDetailsButton();
	} catch (error) {
		if (this._patientContextRequest !== request) return;
		this.patientContext = blankPatientContext();
		this.syncOwnerDetailsButton();
		frappe.show_alert({ message: error?.message || 'Pet owner information could not load.', indicator: 'orange' });
	}
};

const originalTreatmentRowLocked = VetEdgeClinicalWorkspace.methods?.treatmentRowLocked;
VetEdgeClinicalWorkspace.methods.treatmentRowLocked = function treatmentRowLockedWithSourceProtection(row) {
	const sourceGenerated = Boolean(
		row?.source_document
		|| row?.source_detail_name
		|| ['Consultation', 'Lab Order', 'Vaccination'].includes(row?.source_type)
	);
	return sourceGenerated || originalTreatmentRowLocked?.call(this, row) === true;
};

const originalApplyDetail = VetEdgeClinicalWorkspace.methods?.applyDetail;
VetEdgeClinicalWorkspace.methods.applyDetail = function applyDetailWithOwnershipAndOwnerContext(payload) {
	originalApplyDetail.call(this, payload);
	const values = payload?.values || {};
	this.patientContext = {
		patient: { name: values.patient || '', label: payload?.patient_label || values.patient || '' },
		owner: { name: values.primary_owner || '', label: values.primary_owner_label || values.primary_owner || '' },
	};
	if (this.form.patient) this.loadPatientOwnerContext(this.form.patient, false);
	else this.syncOwnerDetailsButton();
	const assignedDoctor = this.form.consulting_practitioner || '';
	if (restrictedDoctor() && assignedDoctor && assignedDoctor !== currentUser()) {
		this.detail.can_write = false;
		this.detail.actions = [];
		this.detail.capabilities.create_vitals = false;
	}
};

const originalStartNewConsultation = VetEdgeClinicalWorkspace.methods?.startNewConsultation;
VetEdgeClinicalWorkspace.methods.startNewConsultation = function startNewConsultationWithDoctorOwnership() {
	originalStartNewConsultation.call(this);
	this.patientContext = blankPatientContext();
	this.syncOwnerDetailsButton();
	if (restrictedDoctor()) this.form.consulting_practitioner = currentUser();
};

const originalBackToList = VetEdgeClinicalWorkspace.methods?.backToList;
VetEdgeClinicalWorkspace.methods.backToList = function backToListWithContextReset() {
	this.patientContext = blankPatientContext();
	document.querySelector('.vetedge-owner-details-button')?.remove();
	return originalBackToList.call(this);
};

const originalUpdateField = VetEdgeClinicalWorkspace.methods?.updateField;
VetEdgeClinicalWorkspace.methods.updateField = function updateFieldWithPatientContext(field, value) {
	originalUpdateField.call(this, field, value);
	if (field === 'patient') this.loadPatientOwnerContext(value || '');
};

const originalLinkSearch = VetEdgeClinicalWorkspace.methods?.linkSearch;
VetEdgeClinicalWorkspace.methods.linkSearch = async function clinicalContextAwareLinkSearch(kind, search) {
	if (['practitioner', 'consultation_type'].includes(kind)) {
		const selected = kind === 'practitioner'
			? (this.form.consulting_practitioner || this.filters.practitioner || '')
			: (this.form.consultation_type || '');
		const effectiveSearch = String(search || '') === String(selected || '') ? '' : search;
		return (await call(CLINICAL_CONTEXT_API.options, { kind, search: effectiveSearch || '', limit: 50 })) || [];
	}
	return originalLinkSearch.call(this, kind, search);
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
