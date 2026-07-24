import { defineComponent, h, reactive } from 'vue';

import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import { applyWorkspaceSafety } from './vetedge_workspace_safety';

const CLINICAL_CONTEXT_API = Object.freeze({
	options: 'vetedge.services.clinical_workspace_context.get_clinical_context_options',
	patientOwner: 'vetedge.services.clinical_workspace_context.get_patient_owner_context',
});
const ELEVATED_ROLES = new Set(['System Manager', 'VetEdge Administrator']);
const patientLabelById = reactive(new Map());
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

function createClinicalLinkField(baseComponent) {
	return defineComponent({
		name: 'VetEdgeClinicalLinkField',
		inheritAttrs: false,
		props: baseComponent?.props || {},
		setup(props, { attrs, slots }) {
			return () => {
				const patientLabel = props.label === 'Patient'
					? patientLabelById.get(String(props.modelValue || '')) || ''
					: '';
				return h(
					baseComponent,
					{
						...attrs,
						...props,
						selectedLabel: props.selectedLabel || patientLabel,
					},
					slots,
				);
			};
		},
	});
}

const originalData = VetEdgeClinicalWorkspace.data;
VetEdgeClinicalWorkspace.data = function clinicalWorkspaceDataWithPatientContext() {
	const state = originalData.call(this) || {};
	return { ...state, patientContext: blankPatientContext() };
};

VetEdgeClinicalWorkspace.computed = VetEdgeClinicalWorkspace.computed || {};
VetEdgeClinicalWorkspace.computed.isRestrictedDoctor = restrictedDoctor;
const originalDetailSubtitle = VetEdgeClinicalWorkspace.computed.detailSubtitle;
VetEdgeClinicalWorkspace.computed.detailSubtitle = function clinicalDetailSubtitleWithOwner() {
	return originalDetailSubtitle?.call(this) || 'Clinical consultation capture';
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
	].filter(([, value]) => value);
	const message = rows.length
		? `<div class="vetedge-owner-details">${rows.map(([label, value]) => `<p><strong>${escapeHtml(label)}:</strong> ${escapeHtml(value)}</p>`).join('')}</div>`
		: '<p>No additional owner details are available.</p>';
	frappe.msgprint({ title: 'Pet Owner Details', message, indicator: 'blue' });
};

VetEdgeClinicalWorkspace.methods.syncOwnerDetailsButton = function syncOwnerDetailsButton() {
	this.$nextTick?.(() => {
		document.querySelector('.vetedge-clinical-statusbar .vetedge-owner-details-button')?.remove();
		const visitPanel = [...document.querySelectorAll('.vetedge-clinical-panel')].find(
			(panel) => panel.querySelector('h3')?.textContent?.trim() === 'Patient and Visit',
		);
		if (!visitPanel) return;

		let summary = visitPanel.querySelector('.vetedge-owner-summary');
		const owner = this.patientContext?.owner || {};
		if (!owner.name && !owner.label) {
			summary?.remove();
			return;
		}

		if (!summary) {
			summary = document.createElement('div');
			summary.className = 'vetedge-owner-summary';
			Object.assign(summary.style, {
				display: 'flex',
				alignItems: 'center',
				justifyContent: 'space-between',
				gap: '1rem',
				padding: '0.75rem 1rem',
				margin: '0.5rem 0 1rem',
				border: '1px solid var(--border-color, #dfe3e8)',
				borderRadius: '0.75rem',
				background: 'var(--card-bg, #fff)',
			});
			visitPanel.querySelector('h3')?.insertAdjacentElement('afterend', summary);
		}

		summary.innerHTML = `
			<div class="vetedge-owner-summary__content">
				<small style="display:block; opacity:.7; margin-bottom:.2rem;">Pet Owner</small>
				<strong class="vetedge-owner-summary__name">${escapeHtml(owner.label || owner.name)}</strong>
				${owner.mobile_no ? `<span class="vetedge-owner-summary__phone" style="display:block; margin-top:.2rem;">${escapeHtml(owner.mobile_no)}</span>` : ''}
			</div>
			<button type="button" class="edge-button edge-button--compact vetedge-owner-details-button">View Owner Details</button>
		`;
		summary.querySelector('.vetedge-owner-details-button').onclick = () => this.showOwnerDetails();
	});
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
		const patientLabel = context?.patient?.label || context?.patient?.name || patient;
		if (patientLabel) patientLabelById.set(String(patient), String(patientLabel));
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

const originalApplyDetail = VetEdgeClinicalWorkspace.methods?.applyDetail;
VetEdgeClinicalWorkspace.methods.applyDetail = function applyDetailWithOwnershipAndOwnerContext(payload) {
	originalApplyDetail.call(this, payload);
	const values = payload?.values || {};
	const patientLabel = payload?.patient_label || values.patient || '';
	if (values.patient && patientLabel) patientLabelById.set(String(values.patient), patientLabel);
	this.patientContext = {
		patient: { name: values.patient || '', label: patientLabel },
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
	document.querySelector('.vetedge-owner-summary')?.remove();
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
	const options = await originalLinkSearch.call(this, kind, search);
	if (kind === 'patient') {
		for (const option of options || []) {
			const value = option?.value || option?.name || option?.[0];
			const label = option?.label || option?.title || option?.[1] || value;
			if (value && label) patientLabelById.set(String(value), String(label));
		}
	}
	return options;
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

const originalActiveTabWatch = VetEdgeClinicalWorkspace.watch?.activeTab;
VetEdgeClinicalWorkspace.watch = {
	...(VetEdgeClinicalWorkspace.watch || {}),
	activeTab(value, previous) {
		if (typeof originalActiveTabWatch === 'function') originalActiveTabWatch.call(this, value, previous);
		if (value === 'visit') this.syncOwnerDetailsButton();
	},
};

applyWorkspaceSafety(VetEdgeClinicalWorkspace, { guardNavigation: true });

export function mountVetEdgeClinicalWorkspace(target) {
	const runtime = window.EdgeSuiteUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	if (!runtime.components?.EdgeLinkField) {
		VetEdgeClinicalWorkspace.components = runtime.components;
	} else {
		VetEdgeClinicalWorkspace.components = {
			...runtime.components,
			EdgeLinkField: createClinicalLinkField(runtime.components.EdgeLinkField),
		};
	}
	const app = runtime.createEdgeApp(VetEdgeClinicalWorkspace);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	window.VetEdgeClinicalWorkspace = VetEdgeClinicalWorkspace;
	window.mountVetEdgeClinicalWorkspace = mountVetEdgeClinicalWorkspace;
}

export default VetEdgeClinicalWorkspace;