import VetEdgeClinicalWorkspace from './vetedge_clinical_workspace/VetEdgeClinicalWorkspace.vue';
import VetEdgeMedicalHistoryModal from './vetedge_clinical_workspace/VetEdgeMedicalHistoryModal.vue';

const RELATED_MODAL_CONFIG = Object.freeze({
	'Veterinary Lab Order': {
		title: 'Laboratory Orders',
		relation: 'consultation',
		fields: ['name', 'status', 'requested_on', 'requested_by', 'linked_invoice'],
		columns: [
			{ fieldname: 'name', label: 'Lab Order' },
			{ fieldname: 'status', label: 'Status', fieldtype: 'Status' },
			{ fieldname: 'requested_on', label: 'Requested On', fieldtype: 'Datetime' },
			{ fieldname: 'requested_by', label: 'Requested By' },
			{ fieldname: 'linked_invoice', label: 'Invoice' },
		],
	},
	'Veterinary Vaccination Record': {
		title: 'Vaccinations',
		relation: 'linked_consultation',
		fields: ['name', 'status', 'vaccine', 'administered_on', 'next_due_date', 'linked_invoice'],
		columns: [
			{ fieldname: 'name', label: 'Vaccination' },
			{ fieldname: 'status', label: 'Status', fieldtype: 'Status' },
			{ fieldname: 'vaccine', label: 'Vaccine' },
			{ fieldname: 'administered_on', label: 'Administered On', fieldtype: 'Datetime' },
			{ fieldname: 'next_due_date', label: 'Next Due', fieldtype: 'Date' },
			{ fieldname: 'linked_invoice', label: 'Invoice' },
		],
	},
	'Veterinary Hospitalisation': {
		title: 'Hospitalisation',
		relation: 'linked_consultation',
		fields: ['name', 'status', 'admission_datetime', 'care_level', 'care_location', 'sales_invoice'],
		columns: [
			{ fieldname: 'name', label: 'Hospitalisation' },
			{ fieldname: 'status', label: 'Status', fieldtype: 'Status' },
			{ fieldname: 'admission_datetime', label: 'Admitted On', fieldtype: 'Datetime' },
			{ fieldname: 'care_level', label: 'Care Level' },
			{ fieldname: 'care_location', label: 'Care Location' },
			{ fieldname: 'sales_invoice', label: 'Invoice' },
		],
	},
});

function showRelatedRecords(view, doctype) {
	const config = RELATED_MODAL_CONFIG[doctype];
	const consultation = String(view.detail?.name || '').trim();
	if (!config || !consultation || !window.VetEdgeEdgeModalPresenter?.open) return;
	const modal = window.VetEdgeEdgeModalPresenter.open({
		title: typeof __ === 'function' ? __(config.title) : config.title,
		subtitle: typeof __ === 'function'
			? __('Records linked to consultation {0}', [consultation])
			: `Records linked to consultation ${consultation}`,
		size: 'lg',
		loading: true,
		loadingMessage: typeof __ === 'function' ? __('Loading related records...') : 'Loading related records...',
	});
	frappe.call({
		method: 'frappe.client.get_list',
		args: {
			doctype,
			filters: { [config.relation]: consultation },
			fields: config.fields,
			order_by: 'modified desc',
			limit_page_length: 50,
		},
		callback(response) {
			modal.update({
				loading: false,
				columns: config.columns.map((column) => ({ ...column, label: typeof __ === 'function' ? __(column.label) : column.label })),
				rows: response.message || [],
				rowKey: 'name',
				emptyTitle: typeof __ === 'function' ? __('No related records') : 'No related records',
				emptyDescription: typeof __ === 'function'
					? __('No {0} are linked to this consultation.', [config.title.toLowerCase()])
					: `No ${config.title.toLowerCase()} are linked to this consultation.`,
			});
		},
		error(error) {
			modal.update({
				loading: false,
				error: error?.message || (typeof __ === 'function' ? __('Related clinical records could not be loaded.') : 'Related clinical records could not be loaded.'),
				errorTitle: typeof __ === 'function' ? __('Related records unavailable') : 'Related records unavailable',
			});
		},
	});
}

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
			openRelated(doctype) {
				showRelatedRecords(this, doctype);
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
