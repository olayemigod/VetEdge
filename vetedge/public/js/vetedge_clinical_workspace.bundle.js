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
	const ownerDetails = [
		owner.label ? `Owner: ${owner.label}` : '',
		owner.mobile_no ? `Tel: ${owner.mobile_no}` : '',
		owner.email_id ? `Email: ${owner.email_id}` : '',
	].filter(Boolean);
	return [base, ...ownerDetails].filter(Boolean).join(' · ');
};

VetEdgeClinicalWorkspace.methods.loadPatientOwnerContext = async function loadPatientOwnerContext(patient, applyDefaultBranch = true) {
	const request = Symbol('patient-context');
	this._patientContextRequest = request;
	if (!patient) {
		this.patientContext = blankPatientContext();
		this.form.primary_owner = '';
		this.form.primary_owner_label = '';
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
	} catch (error) {
		if (this._patientContextRequest !== request) return;
		this.patientContext = blankPatientContext();
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
	if (restrictedDoctor()) this.form.consulting_practitioner = currentUser();
};

const originalBackToList = VetEdgeClinicalWorkspace.methods?.backToList;
VetEdgeClinicalWorkspace.methods.backToList = function backToListWithContextReset() {
	this.patientContext = blankPatientContext();
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
