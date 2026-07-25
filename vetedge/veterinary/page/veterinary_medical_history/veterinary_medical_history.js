frappe.pages['veterinary-medical-history'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Medical History'),
		single_column: true,
	});
	wrapper.page = page;
	wrapper.medical_history_view = new VetEdgeMedicalHistory(page);
	frappe.require('/assets/vetedge/js/vetedge_medical_history_ui.js?v=20260725-1', () => {
		wrapper.medical_history_view.setup();
	});
};

frappe.pages['veterinary-medical-history'].on_page_show = function(wrapper) {
	const view = wrapper.medical_history_view;
	if (view?.ready && view.patient?.get_value()) view.refresh();
};

class VetEdgeMedicalHistory {
	constructor(page) {
		this.page = page;
		this.ready = false;
		this.request_id = 0;
		this.body = $('<div class="vetedge-medical-history-page"></div>').appendTo(page.body);
	}

	setup() {
		if (this.ready) return;
		this.ready = true;
		this.patient = this.page.add_field({
			fieldname: 'patient',
			label: __('Patient'),
			fieldtype: 'Link',
			options: 'Veterinary Patient',
			reqd: 1,
			change: () => this.refresh(),
			get_query: () => ({ filters: { status: ['!=', 'Deceased'] } }),
		});
		this.from_date = this.page.add_field({
			fieldname: 'from_date',
			label: __('From Date'),
			fieldtype: 'Date',
			default: frappe.datetime.add_days(frappe.datetime.get_today(), -90),
			change: () => this.refresh(),
		});
		this.to_date = this.page.add_field({
			fieldname: 'to_date',
			label: __('To Date'),
			fieldtype: 'Date',
			default: frappe.datetime.get_today(),
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__('Refresh'), () => this.refresh());

		const routePatient = frappe.route_options?.patient;
		if (routePatient) {
			this.patient.set_value(routePatient);
			frappe.route_options = null;
		}
		this.render_empty_state();
		if (this.patient.get_value()) this.refresh();
	}

	render_empty_state() {
		this.body.html(`
			<div class="frappe-card p-4">
				<h4>${__('Select a Veterinary Patient')}</h4>
				<p class="text-muted mb-0">${__('Choose a patient and date range to review vital trends and the complete medical history grouped by date.')}</p>
			</div>
		`);
	}

	async refresh() {
		if (!this.ready || !window.VetEdgeMedicalHistoryUI) return;
		const patient = this.patient.get_value();
		if (!patient) {
			this.render_empty_state();
			return;
		}
		const fromDate = this.from_date.get_value();
		const toDate = this.to_date.get_value();
		if (fromDate && toDate && fromDate > toDate) {
			frappe.msgprint(__('From Date cannot be after To Date.'));
			return;
		}
		const requestId = ++this.request_id;
		this.body.html(`<div class="frappe-card p-4 text-center text-muted">${__('Loading medical history...')}</div>`);
		try {
			const data = await window.VetEdgeMedicalHistoryUI.fetchHistory(patient, fromDate, toDate, 100);
			if (requestId !== this.request_id) return;
			window.VetEdgeMedicalHistoryUI.render(this.body[0], data);
		} catch (error) {
			if (requestId !== this.request_id) return;
			this.body.html(`
				<div class="alert alert-danger">
					${frappe.utils.escape_html(error?.message || __('Medical history could not load.'))}
				</div>
			`);
		}
	}
}
