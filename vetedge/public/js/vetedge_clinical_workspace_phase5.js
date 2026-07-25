(() => {
	const API = Object.freeze({
		dispensaryContext: 'vetedge.services.clinical_workspace_phase5.get_dispensary_workspace_context',
		confirmDispensary: 'vetedge.services.clinical_workspace_phase5.confirm_workspace_dispensary',
		treatmentOrder: 'vetedge.services.clinical_workspace_phase5.get_treatment_display_order',
	});
	const DEFAULT_CONSULTATION_SOURCE_DETAIL = 'Default Consultation Fee';
	const call = (method, args = {}) => frappe.call({ method, args }).then((response) => response.message);
	const errorMessage = (error, fallback) => error?.message || error?._server_messages || error?.exc_type || fallback;
	const escapeHtml = (value) => frappe.utils.escape_html(String(value ?? ''));

	function isDefaultConsultationRow(row, defaultDetail = DEFAULT_CONSULTATION_SOURCE_DETAIL) {
		return Boolean(row?.source_type === 'Consultation' && row?.source_detail_name === defaultDetail);
	}

	function install(component = window.VetEdgeClinicalWorkspace) {
		if (!component?.methods || component.__vetedgePhase5Installed) return component;
		component.__vetedgePhase5Installed = true;

		const originalApplyDetail = component.methods.applyDetail;
		component.methods.applyDetail = function applyDetailWithPhase5(payload) {
			originalApplyDetail.call(this, payload);
			if ((this.form?.dispensary_status || '') === 'Pending Dispensary') {
				this.detail.actions = (this.detail.actions || []).filter(
					(action) => !['status:Ready for Treatment', 'status:Completed'].includes(action?.key),
				);
			}
			this.syncDispensaryAction();
			this.refreshTreatmentDisplayOrder();
		};

		component.methods.syncDispensaryAction = function syncDispensaryAction() {
			this.$nextTick?.(() => {
				document.querySelector('.vetedge-clinical-actions .vetedge-dispensary-workspace-action')?.remove();
				if (!this.detail?.open || this.isNew) return;
				const status = this.form?.dispensary_status || 'Not Required';
				const stockEntry = this.form?.dispensary_stock_entry || '';
				if (status !== 'Pending Dispensary' && !stockEntry) return;
				const actionArea = document.querySelector('.vetedge-clinical-actions');
				if (!actionArea) return;
				const button = document.createElement('button');
				button.type = 'button';
				button.className = 'edge-button vetedge-dispensary-workspace-action';
				button.textContent = status === 'Pending Dispensary' ? __('Review Dispensary') : __('Open Stock Entry');
				button.disabled = Boolean(this.busy);
				button.onclick = () => {
					if (status === 'Pending Dispensary') this.openDispensaryWorkspace();
					else if (stockEntry) this.openDocument('Stock Entry', stockEntry);
				};
				const saveButton = actionArea.querySelector('.edge-button--primary');
				if (saveButton) actionArea.insertBefore(button, saveButton);
				else actionArea.appendChild(button);
			});
		};

		component.methods.openDispensaryWorkspace = function openDispensaryWorkspace() {
			if (this.busy || this.isNew) return;
			const open = () => this.showDispensaryWorkspaceDialog();
			if (!this.dirty) {
				open();
				return;
			}
			frappe.confirm(
				__('Save consultation changes before reviewing the dispensary issue?'),
				() => Promise.resolve(this.saveConsultation()).then((saved) => saved && open()),
				() => frappe.msgprint(__('Please save or discard consultation changes before confirming dispensary.')),
			);
		};

		component.methods.showDispensaryWorkspaceDialog = async function showDispensaryWorkspaceDialog() {
			if (!this.detail?.name) return;
			this.busy = true;
			let context;
			try {
				context = await call(API.dispensaryContext, { consultation: this.detail.name });
			} catch (error) {
				frappe.msgprint({
					title: __('Dispensary could not load'),
					message: errorMessage(error, __('Unable to load dispensary details.')),
					indicator: 'red',
				});
				this.busy = false;
				return;
			}
			this.busy = false;

			const pending = context?.status === 'Pending Dispensary';
			const hasStockItems = (context?.items || []).some((row) => Number(row.stock_item || 0) === 1);
			const canConfirm = Boolean(pending && context?.can_confirm && (!hasStockItems || context?.warehouse));
			const dialog = new frappe.ui.Dialog({
				title: pending ? __('Review Dispensary Issue') : __('Dispensary Details'),
				size: 'extra-large',
				fields: [
					{
						fieldname: 'summary_html',
						fieldtype: 'HTML',
						options: `
							<div class="frappe-card p-3 mb-3">
								<div class="row">
									<div class="col-md-3"><small class="text-muted">${__('Patient')}</small><div><strong>${escapeHtml(context.patient_label || context.patient)}</strong></div></div>
									<div class="col-md-3"><small class="text-muted">${__('Branch')}</small><div><strong>${escapeHtml(context.service_branch || __('Not Set'))}</strong></div></div>
									<div class="col-md-3"><small class="text-muted">${__('Warehouse')}</small><div><strong>${escapeHtml(context.warehouse || __('Not Configured'))}</strong></div></div>
									<div class="col-md-3"><small class="text-muted">${__('Status')}</small><div><strong>${escapeHtml(context.status)}</strong></div></div>
								</div>
								<p class="text-muted mt-3 mb-0">${escapeHtml(context.guidance || '')}</p>
								${hasStockItems && !context.warehouse ? `<div class="alert alert-danger mt-3 mb-0">${__('Configure a dispensary warehouse for this branch before confirmation.')}</div>` : ''}
								${pending && !context.can_confirm ? `<div class="alert alert-warning mt-3 mb-0">${__('Your role can review this requirement but cannot confirm stock dispensing.')}</div>` : ''}
							</div>
						`,
					},
					{
						fieldname: 'items',
						fieldtype: 'Table',
						label: __('Items to Dispense'),
						cannot_add_rows: true,
						cannot_delete_rows: true,
						in_place_edit: true,
						data: context.items || [],
						fields: [
							{ fieldname: 'planned_treatment_row', fieldtype: 'Data', hidden: 1 },
							{ fieldname: 'item', fieldtype: 'Link', options: 'Item', label: __('Item'), read_only: 1, in_list_view: 1, columns: 3 },
							{ fieldname: 'item_name', fieldtype: 'Data', label: __('Item Name'), read_only: 1, in_list_view: 1, columns: 3 },
							{ fieldname: 'planned_qty', fieldtype: 'Float', label: __('Planned Qty'), read_only: 1, in_list_view: 1, columns: 2 },
							{ fieldname: 'dispensed_qty', fieldtype: 'Float', label: __('Dispensed Qty'), reqd: 1, read_only: canConfirm ? 0 : 1, in_list_view: 1, columns: 2 },
							{ fieldname: 'uom', fieldtype: 'Link', options: 'UOM', label: __('UOM'), read_only: 1, in_list_view: 1, columns: 2 },
							{ fieldname: 'selected_batch', fieldtype: 'Link', options: 'Batch', label: __('Selected Batch'), read_only: 1 },
							{ fieldname: 'notes', fieldtype: 'Small Text', label: __('Notes'), read_only: canConfirm ? 0 : 1 },
						],
					},
					{
						fieldname: 'stock_html',
						fieldtype: 'HTML',
						options: context.stock_entry
							? `<button type="button" class="btn btn-default btn-sm" data-open-dispensary-stock-entry="${escapeHtml(context.stock_entry)}">${__('Open Stock Entry')} ${escapeHtml(context.stock_entry)}</button>`
							: `<p class="text-muted">${__('Batch allocation and stock availability are validated by VetEdge during confirmation.')}</p>`,
					},
				],
				primary_action_label: canConfirm ? __('Confirm Dispensary Issue') : __('Close'),
				primary_action: async () => {
					if (!canConfirm) {
						dialog.hide();
						return;
					}
					const rows = dialog.get_value('items') || [];
					if (!rows.length || rows.some((row) => Number(row.dispensed_qty || 0) <= 0)) {
						frappe.msgprint(__('Every dispensary item must have a Dispensed Qty greater than zero.'));
						return;
					}
					dialog.get_primary_btn().prop('disabled', true);
					try {
						const result = await call(API.confirmDispensary, {
							consultation: this.detail.name,
							dispensed_items: JSON.stringify(rows),
							modified: context.modified || this.detail.modified,
						});
						if (result?.detail) this.applyDetail(result.detail);
						dialog.hide();
						frappe.show_alert({ message: __('Dispensary issue confirmed.'), indicator: 'green' });
					} catch (error) {
						frappe.msgprint({
							title: __('Dispensary confirmation failed'),
							message: errorMessage(error, __('Unable to confirm the dispensary issue.')),
							indicator: 'red',
						});
						dialog.get_primary_btn().prop('disabled', false);
					}
				},
			});
			dialog.show();
			dialog.$wrapper.find('[data-open-dispensary-stock-entry]').on('click', (event) => {
				const name = event.currentTarget.getAttribute('data-open-dispensary-stock-entry');
				if (name) this.openDocument('Stock Entry', name);
			});
		};

		component.methods.refreshTreatmentDisplayOrder = async function refreshTreatmentDisplayOrder() {
			if (!this.detail?.name || !(this.form?.planned_treatments || []).length) return;
			const request = Symbol('treatment-order');
			this._phase5TreatmentOrderRequest = request;
			try {
				const result = await call(API.treatmentOrder, { consultation: this.detail.name });
				if (this._phase5TreatmentOrderRequest !== request) return;
				const rows = this.form?.planned_treatments || [];
				const rank = new Map((result?.order || []).map((name, index) => [name, index]));
				const defaultDetail = result?.default_consultation_source_detail || DEFAULT_CONSULTATION_SOURCE_DETAIL;
				this.form.planned_treatments = [...rows].sort((left, right) => {
					const leftDefault = isDefaultConsultationRow(left, defaultDetail);
					const rightDefault = isDefaultConsultationRow(right, defaultDetail);
					if (leftDefault !== rightDefault) return leftDefault ? 1 : -1;
					if (!left?.name || !right?.name) return Number(right?._client_added_at || 0) - Number(left?._client_added_at || 0);
					return (rank.get(left.name) ?? Number.MAX_SAFE_INTEGER) - (rank.get(right.name) ?? Number.MAX_SAFE_INTEGER);
				});
			} catch (error) {
				console.warn('Treatment display order could not load:', error);
			}
		};

		const originalAddTreatment = component.methods.addTreatment;
		component.methods.addTreatment = function addTreatmentNewestFirst() {
			const before = this.form?.planned_treatments?.length || 0;
			const result = originalAddTreatment?.call(this);
			const rows = this.form?.planned_treatments || [];
			if (rows.length > before) {
				const added = rows.pop();
				added._client_added_at = Date.now();
				rows.unshift(added);
			}
			return result;
		};

		component.methods.openHistory = function openDateGroupedMedicalHistory() {
			if (!this.form?.patient || !window.VetEdgeMedicalHistoryUI?.openDialog) return;
			this.historyDialog = { ...(this.historyDialog || {}), open: true, loading: false, data: {} };
			window.VetEdgeMedicalHistoryUI.openDialog({
				patient: this.form.patient,
				patientLabel: this.patientContext?.patient?.label || this.form.patient,
				onClose: () => {
					this.historyDialog = { ...(this.historyDialog || {}), open: false, loading: false, data: {} };
				},
			});
		};

		return component;
	}

	window.VetEdgeClinicalWorkspacePhase5 = Object.freeze({
		version: '1.0.0',
		install,
	});
})();
