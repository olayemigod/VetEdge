import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import VetEdgeMedicalHistoryModal from './vetedge_clinical_workspace/VetEdgeMedicalHistoryModal.vue';

const RELATED_MODAL_CONFIG = Object.freeze({
	'Veterinary Lab Order': {
		title: 'Laboratory Orders', relation: 'consultation', createLabel: 'Add Lab Order',
		fields: ['name', 'status', 'requested_on', 'requested_by', 'linked_invoice'],
		columns: [
			{ fieldname: 'name', label: 'Lab Order' }, { fieldname: 'status', label: 'Status', fieldtype: 'Status' },
			{ fieldname: 'requested_on', label: 'Requested On', fieldtype: 'Datetime' }, { fieldname: 'requested_by', label: 'Requested By' },
			{ fieldname: 'linked_invoice', label: 'Invoice' },
		],
	},
	'Veterinary Vaccination Record': {
		title: 'Vaccinations', relation: 'linked_consultation', createLabel: 'New Vaccination',
		fields: ['name', 'status', 'vaccine', 'administered_on', 'next_due_date', 'linked_invoice'],
		columns: [
			{ fieldname: 'name', label: 'Vaccination' }, { fieldname: 'status', label: 'Status', fieldtype: 'Status' },
			{ fieldname: 'vaccine', label: 'Vaccine' }, { fieldname: 'administered_on', label: 'Administered On', fieldtype: 'Datetime' },
			{ fieldname: 'next_due_date', label: 'Next Due', fieldtype: 'Date' }, { fieldname: 'linked_invoice', label: 'Invoice' },
		],
	},
	'Veterinary Hospitalisation': {
		title: 'Hospitalisation', relation: 'linked_consultation', createLabel: 'Admit for Hospitalisation',
		fields: ['name', 'status', 'admission_datetime', 'care_level', 'care_location', 'sales_invoice'],
		columns: [
			{ fieldname: 'name', label: 'Hospitalisation' }, { fieldname: 'status', label: 'Status', fieldtype: 'Status' },
			{ fieldname: 'admission_datetime', label: 'Admitted On', fieldtype: 'Datetime' }, { fieldname: 'care_level', label: 'Care Level' },
			{ fieldname: 'care_location', label: 'Care Location' }, { fieldname: 'sales_invoice', label: 'Invoice' },
		],
	},
});

const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message || {});
const tr = (value) => typeof __ === 'function' ? __(value) : value;
const serverDatetime = (value) => value ? String(value).replace('T', ' ') : value;

function canCreateRelated(view, doctype) {
	if (!view?.detail?.can_write || !view?.detail?.name) return false;
	if (doctype === 'Veterinary Hospitalisation') return !['Completed', 'Cancelled'].includes(String(view.detail.status || ''));
	return !view.detail.scope_locked && !['Completed', 'Cancelled'].includes(String(view.detail.status || ''));
}

async function fetchRelatedRows(doctype, config, consultation) {
	return await call('frappe.client.get_list', {
		doctype, filters: { [config.relation]: consultation }, fields: config.fields,
		order_by: 'modified desc', limit_page_length: 50,
	});
}

function showRelatedRecords(view, doctype) {
	const config = RELATED_MODAL_CONFIG[doctype];
	const consultation = String(view.detail?.name || '').trim();
	if (!config || !consultation || !window.VetEdgeEdgeModalPresenter?.open) return;
	const modal = window.VetEdgeEdgeModalPresenter.open({ title: tr(config.title), subtitle: consultation, size: 'lg', loading: true, loadingMessage: tr('Loading related records...') });
	const refresh = async () => {
		modal.update({ loading: true, error: '' });
		try {
			const rows = await fetchRelatedRows(doctype, config, consultation);
			const actions = canCreateRelated(view, doctype) ? [{ label: tr(config.createLabel), primary: true, closeOnSuccess: false, onClick: () => openCreateRelated(view, doctype, refresh) }] : [];
			modal.update({
				loading: false, error: '',
				title: tr(config.title), subtitle: typeof __ === 'function' ? __('Records linked to consultation {0}', [consultation]) : consultation,
				columns: config.columns.map((column) => ({ ...column, label: tr(column.label) })), rows: rows || [], rowKey: 'name',
				emptyTitle: tr('No related records'), emptyDescription: typeof __ === 'function' ? __('No {0} are linked to this consultation.', [config.title.toLowerCase()]) : '',
				actions,
			});
		} catch (error) {
			modal.update({ loading: false, error: error?.message || tr('Related clinical records could not be loaded.'), errorTitle: tr('Related records unavailable'), onRetry: refresh });
		}
	};
	refresh();
}

function openCreateRelated(view, doctype, refreshParent) {
	if (doctype === 'Veterinary Lab Order') return openLabOrderModal(view, refreshParent);
	if (doctype === 'Veterinary Vaccination Record') return openVaccinationModal(view, refreshParent);
	if (doctype === 'Veterinary Hospitalisation') return openHospitalisationModal(view, refreshParent);
}

async function finishRelatedCreate(view, refreshParent, successMessage) {
	await view.loadDetail?.(view.detail.name);
	await refreshParent?.();
	frappe.show_alert({ message: tr(successMessage), indicator: 'green' });
}

function openLabOrderModal(view, refreshParent) {
	const consultation = view.detail.name;
	const modal = window.VetEdgeEdgeModalPresenter.open({ title: tr('Add Lab Order'), subtitle: consultation, size: 'lg', loading: true, loadingMessage: tr('Loading available laboratory tests...') });
	call('vetedge.services.lab.get_active_lab_tests_for_picker').then((tests) => {
		const options = (tests || []).map((row) => ({ value: row.name, label: row.test_name || row.name, description: [row.sample_type, row.linked_item].filter(Boolean).join(' · ') }));
		modal.update({
			loading: false,
			fields: [
				{ fieldname: 'lab_tests', label: tr('Laboratory Tests'), type: 'multiselect', required: true, options, emptyMessage: tr('No active laboratory tests are available.') },
				{ fieldname: 'sample_notes', label: tr('Sample / Clinical Notes'), type: 'textarea', rows: 3 },
			],
			values: { lab_tests: [], sample_notes: '' },
			actions: [{ label: tr('Create Lab Order'), primary: true, async onClick(values) {
				if (!(values.lab_tests || []).length) { modal.update({ error: tr('Select at least one laboratory test.'), errorTitle: tr('Laboratory test required') }); return; }
				modal.update({ busy: true, error: '' });
				try {
					await call('vetedge.services.lab.create_lab_order_from_consultation', { consultation, sample_notes: values.sample_notes || undefined, lab_tests: values.lab_tests.map((name) => ({ lab_test_template: name })) });
					await finishRelatedCreate(view, refreshParent, 'Lab order created.');
				} catch (error) { modal.update({ busy: false, error: error?.message || tr('Lab order could not be created.'), errorTitle: tr('Lab order failed') }); }
			} }],
		});
	}).catch((error) => modal.update({ loading: false, error: error?.message || tr('Laboratory tests could not be loaded.'), errorTitle: tr('Laboratory tests unavailable') }));
}

async function searchLink(doctype, query, filters = {}) {
	const payload = await call('frappe.desk.search.search_link', { doctype, txt: String(query || ''), filters, page_length: 20 });
	const rows = Array.isArray(payload) ? payload : payload?.results || [];
	return rows.map((row) => typeof row === 'string' ? { value: row, label: row } : { value: row.value || row.name, label: row.description || row.label || row.value || row.name, description: row.description && row.description !== (row.value || row.name) ? row.value || row.name : '' }).filter((row) => row.value);
}

function vaccinationFields(view, modal) {
	return [
		{
			fieldname: 'vaccine', label: tr('Vaccine'), type: 'link', required: true, placeholder: tr('Search active vaccines'),
			searcher: (query) => searchLink('Veterinary Vaccine', query, { is_active: 1 }),
			async onChange(value, values) {
				if (!value) return;
				try {
					const defaults = await call('vetedge.services.vaccination.get_vaccination_billing_defaults', { vaccine: value, company: view.form?.company || undefined, customer: view.form?.primary_owner || undefined, branch: view.form?.service_branch || undefined });
					modal.update({ values: { ...values, vaccine: value, billing_item: defaults.billing_item || '', rate: defaults.rate ?? 0 }, error: '' });
				} catch (error) { modal.update({ error: error?.message || tr('Vaccination billing defaults could not be loaded.'), errorTitle: tr('Vaccination defaults unavailable') }); }
			},
		},
		{ fieldname: 'billing_item', label: tr('Billing Item'), type: 'text', readOnly: true },
		{ fieldname: 'rate', label: tr('Rate'), type: 'number', min: 0, step: '0.01' },
		{ fieldname: 'dose', label: tr('Dose'), type: 'text' }, { fieldname: 'route', label: tr('Route'), type: 'text' },
		{ fieldname: 'administered_on', label: tr('Administration Date/Time'), type: 'datetime-local' }, { fieldname: 'next_due_date', label: tr('Next Due Date'), type: 'date' },
		{ fieldname: 'notes', label: tr('Notes'), type: 'textarea', rows: 3 },
		{ fieldname: 'create_invoice', label: tr('Create / update billing invoice'), type: 'checkbox', default: 1 },
	];
}

function openVaccinationModal(view, refreshParent) {
	const consultation = view.detail.name;
	const modal = window.VetEdgeEdgeModalPresenter.open({ title: tr('New Vaccination'), subtitle: consultation, size: 'lg', values: { vaccine: '', billing_item: '', rate: '', dose: '', route: '', administered_on: '', next_due_date: '', notes: '', create_invoice: 1 } });
	modal.update({
		fields: vaccinationFields(view, modal),
		actions: [{ label: tr('Create Vaccination'), primary: true, async onClick(values) {
			if (!values.vaccine) { modal.update({ error: tr('Select a vaccine before creating the vaccination record.'), errorTitle: tr('Vaccine required') }); return; }
			modal.update({ busy: true, error: '' });
			try {
				await call('vetedge.services.vaccination.create_vaccination_from_consultation', { consultation, values: { ...values, administered_on: serverDatetime(values.administered_on) || undefined, create_invoice: values.create_invoice ? 1 : 0 } });
				await finishRelatedCreate(view, refreshParent, 'Vaccination record created.');
			} catch (error) { modal.update({ busy: false, error: error?.message || tr('Vaccination record could not be created.'), errorTitle: tr('Vaccination failed') }); }
		} }],
	});
}

function openHospitalisationModal(view, refreshParent) {
	const consultation = view.detail.name;
	const modal = window.VetEdgeEdgeModalPresenter.open({
		title: tr('Admit for Hospitalisation'), subtitle: consultation, size: 'md',
		message: tr('Create or link the active hospitalisation for this consultation. Patient, owner, branch and attending practitioner are derived from the consultation.'),
		actions: [{ label: tr('Admit for Hospitalisation'), primary: true, async onClick() {
			modal.update({ busy: true, error: '' });
			try {
				await call('vetedge.services.hospitalisation.create_hospitalisation_from_consultation', { consultation_name: consultation });
				await finishRelatedCreate(view, refreshParent, 'Hospitalisation created or linked.');
			} catch (error) { modal.update({ busy: false, error: error?.message || tr('Hospitalisation could not be created.'), errorTitle: tr('Hospitalisation failed') }); }
		} }],
	});
}

export function mountVetEdgeClinicalWorkspace(target) {
	const runtime = window.EdgeSuiteUI || window.EdgeUI;
	if (!runtime || typeof runtime.createEdgeApp !== 'function') throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
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
				if (!patient) { this.error = typeof __ === 'function' ? __('Select or save a Veterinary Patient before opening Medical History.') : 'Select or save a Veterinary Patient before opening Medical History.'; return; }
				historyView?.open?.({ patient, patientLabel: this.form?.patient_name || this.form?.patient_label || patient });
			},
			openRelated(doctype) { showRelatedRecords(this, doctype); },
		},
	};
	const app = runtime.createEdgeApp(ClinicalWorkspaceRoot);
	const view = app.mount(target);
	return { view, unmount() { app.unmount(); historyApp.unmount(); historyHost.remove(); } };
}

if (typeof window !== 'undefined') {
	window.VetEdgeClinicalWorkspace = VetEdgeClinicalWorkspace;
	window.VetEdgeMedicalHistoryModal = VetEdgeMedicalHistoryModal;
	window.mountVetEdgeClinicalWorkspace = mountVetEdgeClinicalWorkspace;
}

export default VetEdgeClinicalWorkspace;
