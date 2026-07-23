const API = Object.freeze({
	definition: "vetedge.services.clinical_workspace.get_clinical_definition",
	summary: "vetedge.services.clinical_workspace.get_clinical_summary",
	consultationList: "vetedge.services.clinical_workspace.get_consultation_list",
	consultationDocument: "vetedge.services.clinical_workspace.get_consultation_document",
	consultationSave: "vetedge.services.clinical_workspace.save_consultation_document",
	consultationTransition: "vetedge.services.clinical_workspace.transition_clinical_consultation",
	vitalsList: "vetedge.services.clinical_workspace.get_vitals_list",
	vitalsDocument: "vetedge.services.clinical_workspace.get_vitals_document",
	vitalsSave: "vetedge.services.clinical_workspace.save_vitals_document",
	history: "vetedge.services.clinical_workspace.get_clinical_medical_history",
	link: "vetedge.services.clinical_workspace.get_clinical_link_options",
	patientDefaults: "vetedge.services.clinical_workspace.get_patient_clinical_defaults",
	appointmentContext: "vetedge.services.clinical_workspace.get_consultation_context_from_appointment",
	treatmentDefaults: "vetedge.services.clinical_workspace.get_clinical_treatment_defaults",
	actionOptions: "vetedge.services.clinical_workspace.get_clinical_action_options",
	consultationAction: "vetedge.services.clinical_workspace.perform_consultation_action",
});

const TABS = Object.freeze([
	{ value: "consultations", label: "Consultations", description: "Clinical assessment, diagnosis, treatment and workflow" },
	{ value: "vitals", label: "Vital Signs", description: "Patient observations linked to consultations and branches" },
	{ value: "history", label: "Medical History", description: "Read-only longitudinal patient record" },
]);

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? {}));
}

function errorMessage(error, fallback) {
	return error?.message || error?._server_messages || error?.exc_type || fallback || __("The requested clinical operation could not be completed.");
}

function normalizeDateTimeForInput(value) {
	if (!value || typeof value !== "string") return value;
	return value.length >= 16 ? value.replace(" ", "T").slice(0, 19) : value;
}

function normalizeModelForInput(values) {
	const next = clone(values || {});
	for (const fieldname of ["consultation_datetime", "recorded_on"]) {
		if (next[fieldname]) next[fieldname] = normalizeDateTimeForInput(next[fieldname]);
	}
	return next;
}

function normalizeModelForServer(values) {
	const next = clone(values || {});
	for (const fieldname of ["consultation_datetime", "recorded_on", "administered_on", "appointment_datetime"]) {
		if (next[fieldname] && typeof next[fieldname] === "string") next[fieldname] = next[fieldname].replace("T", " ");
	}
	return next;
}

export default {
	name: "VetEdgeClinicalWorkspace",
	data() {
		const route = new URLSearchParams(window.location.search || "");
		const requested = route.get("tab") || "consultations";
		const tab = TABS.some((option) => option.value === requested) ? requested : "consultations";
		return {
			tab,
			tabOptions: TABS,
			definitions: {},
			summary: {},
			filters: { search: route.get("search") || "", status: "", branch: "", practitioner: "", patient: "", consultation: "" },
			consultationList: { rows: [], total: 0, start: 0, page_length: 25 },
			vitalsList: { rows: [], total: 0, start: 0, page_length: 25 },
			pageLength: 25,
			mode: tab === "history" ? "history" : route.get("name") || route.get("new") === "1" ? "form" : "list",
			document: {},
			model: {},
			originalModel: "{}",
			fieldErrors: {},
			loading: true,
			saving: false,
			actionBusy: false,
			error: "",
			dirty: false,
			historyFilters: { patient: route.get("patient") || "", from_date: route.get("from_date") || "", to_date: route.get("to_date") || "" },
			history: {},
			historyLoaded: false,
			actionDialog: { open: false, kind: "", title: "Clinical action", subtitle: "", message: "", values: {}, options: {}, entries: [], confirmLabel: "Continue", danger: false, action: "" },
			consultationStatuses: ["Draft", "In Progress", "Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled"],
		};
	},
	computed: {
		identity() { return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {}; },
		branchName() { return frappe.boot?.edgesuite_product_menu?.branch || frappe.defaults?.get_user_default?.("branch") || "All Branches"; },
		userName() {
			const user = frappe.session?.user || "";
			const info = frappe.boot?.user_info?.[user] || {};
			return info.fullname || info.full_name || user;
		},
		listMode() { return this.mode === "list"; },
		documentMode() { return this.mode === "form"; },
		documentReady() { return Boolean(this.document?.schema); },
		showSummary() { return this.listMode && this.tab !== "history"; },
		pageTitle() {
			if (this.tab === "history") return "Medical History";
			if (this.listMode) return this.tab === "consultations" ? "Consultations" : "Vital Signs";
			return this.document.title || (this.tab === "consultations" ? "Consultation" : "Vital Signs");
		},
		pageSubtitle() {
			if (this.tab === "history") return "Permission-aware longitudinal clinical record for one patient.";
			if (this.listMode) return this.tab === "consultations"
				? "Manage visit context, clinical findings, treatment planning and controlled workflow actions."
				: "Record and review patient observations with consultation and branch validation.";
			return this.document.name || (this.document.is_new ? "Create a new clinical record" : "Clinical record");
		},
		headerActionLabel() {
			if (!this.listMode || this.tab === "history") return "";
			if (this.tab === "consultations" && this.definitions.consultations?.permissions?.create) return "New Consultation";
			if (this.tab === "vitals" && this.definitions.vitals?.enabled && this.definitions.vitals?.permissions?.create) return "New Vital Signs";
			return "";
		},
		canEdit() {
			if (this.document.is_new) {
				return this.tab === "consultations"
					? Boolean(this.definitions.consultations?.permissions?.create)
					: Boolean(this.definitions.vitals?.permissions?.create);
			}
			return Boolean(this.document.permissions?.write);
		},
		canSave() { return this.canEdit; },
		openAction() { return [{ key: "open", label: "Open", primary: true }]; },
		consultationColumns() { return [{ fieldname: "name", label: "Consultation" }, { fieldname: "patient", label: "Patient" }, { fieldname: "consultation_datetime", label: "Date / Time" }, { fieldname: "status", label: "Status", status: true }]; },
		vitalsColumns() { return [{ fieldname: "name", label: "Vitals" }, { fieldname: "patient", label: "Patient" }, { fieldname: "recorded_on", label: "Recorded On" }, { fieldname: "weight", label: "Weight" }]; },
		actionFormValid() {
			if (this.actionDialog.kind === "follow_up") return Boolean(this.actionDialog.values.appointment_datetime);
			if (this.actionDialog.kind === "lab") return Boolean(this.actionDialog.values.lab_tests?.length);
			if (this.actionDialog.kind === "vaccination") return Boolean(this.actionDialog.values.vaccine);
			if (this.actionDialog.kind === "dispensary") return Boolean(this.actionDialog.values.dispensed_items?.length) && this.actionDialog.values.dispensed_items.every((row) => Number(row.dispensed_qty) > 0);
			if (this.actionDialog.kind === "cancellation") return Boolean(this.actionDialog.options.can_cancel);
			return true;
		},
		trendSummaries() {
			const labels = { temperature: "Temperature", weight: "Weight", heart_rate: "Heart Rate", respiratory_rate: "Respiratory Rate", body_condition_score: "Body Condition" };
			return Object.entries(this.history.trends || {}).map(([key, points]) => ({ key, label: labels[key] || key, points: points?.length || 0, latest: points?.length ? points[points.length - 1].value : "—" }));
		},
		historyConsultationColumns() { return [{ fieldname: "title", label: "Consultation" }, { fieldname: "timestamp", label: "Date / Time" }, { fieldname: "practitioner", label: "Practitioner" }, { fieldname: "service_branch", label: "Branch" }, { fieldname: "status", label: "Status", status: true }]; },
		historyVitalsColumns() { return [{ fieldname: "timestamp", label: "Recorded" }, { fieldname: "weight", label: "Weight" }, { fieldname: "temperature", label: "Temperature" }, { fieldname: "heart_rate", label: "Heart Rate" }, { fieldname: "pain_score", label: "Pain" }]; },
		historyDiagnosisColumns() { return [{ fieldname: "timestamp", label: "Date" }, { fieldname: "diagnosis", label: "Diagnosis" }, { fieldname: "diagnosis_type", label: "Type", status: true }, { fieldname: "practitioner", label: "Practitioner" }, { fieldname: "notes", label: "Notes" }]; },
		historyTreatmentColumns() { return [{ fieldname: "timestamp", label: "Date" }, { fieldname: "item", label: "Item / Service" }, { fieldname: "qty", label: "Qty" }, { fieldname: "uom", label: "UOM" }, { fieldname: "treatment_type", label: "Treatment Type" }, { fieldname: "notes", label: "Notes" }]; },
		historyLabColumns() { return [{ fieldname: "timestamp", label: "Date" }, { fieldname: "title", label: "Lab Order" }, { fieldname: "status", label: "Status", status: true }]; },
		historyVaccinationColumns() { return [{ fieldname: "timestamp", label: "Date" }, { fieldname: "title", label: "Vaccination" }, { fieldname: "status", label: "Status", status: true }, { fieldname: "next_due_date", label: "Next Due" }]; },
		openHistoryConsultationAction() { return [{ key: "open", label: "Open", primary: true }]; },
	},
	mounted() {
		window.addEventListener("popstate", this.handleBrowserNavigation);
		window.addEventListener("beforeunload", this.handleBeforeUnload);
		this.loadCurrentRoute();
	},
	beforeUnmount() {
		window.removeEventListener("popstate", this.handleBrowserNavigation);
		window.removeEventListener("beforeunload", this.handleBeforeUnload);
	},
	methods: {
		async call(method, args = {}) { const response = await frappe.call(method, args); return response?.message; },
		async loadCurrentRoute() {
			this.loading = true;
			this.error = "";
			try {
				if (!Object.keys(this.definitions).length) this.definitions = await this.call(API.definition) || {};
				const route = new URLSearchParams(window.location.search || "");
				const requested = route.get("tab") || this.tab;
				this.tab = TABS.some((option) => option.value === requested) ? requested : "consultations";
				if (this.tab === "history") {
					this.mode = "history";
					this.historyFilters.patient = route.get("patient") || this.historyFilters.patient;
					this.historyFilters.from_date = route.get("from_date") || this.historyFilters.from_date;
					this.historyFilters.to_date = route.get("to_date") || this.historyFilters.to_date;
					if (this.historyFilters.patient) await this.loadHistory(false);
					return;
				}
				this.mode = route.get("name") || route.get("new") === "1" ? "form" : "list";
				if (this.mode === "form") {
					await this.loadDocument(route.get("name") || null);
				} else {
					await Promise.all([this.loadSummary(), this.loadList()]);
				}
			} catch (error) {
				this.error = errorMessage(error, "Unable to load the Clinical Workspace.");
			} finally {
				this.loading = false;
			}
		},
		async loadSummary() { this.summary = await this.call(API.summary, { branch: this.filters.branch || null }) || {}; },
		async loadList() {
			if (this.tab === "consultations") {
				this.consultationList = await this.call(API.consultationList, { search: this.filters.search, status: this.filters.status || null, branch: this.filters.branch || null, practitioner: this.filters.practitioner || null, patient: this.filters.patient || null, start: this.consultationList.start || 0, page_length: this.pageLength }) || this.consultationList;
			} else {
				this.vitalsList = await this.call(API.vitalsList, { search: this.filters.search, branch: this.filters.branch || null, patient: this.filters.patient || null, consultation: this.filters.consultation || null, start: this.vitalsList.start || 0, page_length: this.pageLength }) || this.vitalsList;
			}
		},
		async loadDocument(name) {
			const method = this.tab === "consultations" ? API.consultationDocument : API.vitalsDocument;
			const defaults = this.routeDefaults();
			this.document = await this.call(method, { name, defaults }) || {};
			this.model = normalizeModelForInput(this.document.values || {});
			this.originalModel = JSON.stringify(this.model);
			this.dirty = false;
			this.fieldErrors = {};
		},
		routeDefaults() {
			const route = new URLSearchParams(window.location.search || "");
			const defaults = {};
			for (const fieldname of ["patient", "consultation", "service_branch", "linked_appointment"]) {
				if (route.get(fieldname)) defaults[fieldname] = route.get(fieldname);
			}
			return defaults;
		},
		async reloadCurrentView() { await this.loadCurrentRoute(); },
		async reloadDocument() { if (this.document.name) { this.loading = true; try { await this.loadDocument(this.document.name); } finally { this.loading = false; } } },
		changeTab(next) {
			if (next === this.tab) return;
			this.navigateWithDirtyGuard(() => {
				this.tab = next;
				this.mode = next === "history" ? "history" : "list";
				this.resetDocumentState();
				this.updateRoute({ tab: next });
				this.loadCurrentRoute();
			});
		},
		handleHeaderAction() { if (this.tab === "consultations") this.openNewConsultation(); else if (this.tab === "vitals") this.openNewVitals(); },
		openNewConsultation(defaults = {}) { this.tab = "consultations"; this.mode = "form"; this.updateRoute({ tab: "consultations", new: "1", ...defaults }); this.loadCurrentRoute(); },
		openNewVitals(defaults = {}) { this.tab = "vitals"; this.mode = "form"; this.updateRoute({ tab: "vitals", new: "1", ...defaults }); this.loadCurrentRoute(); },
		openConsultationRow(row) { this.openClinicalRecord("consultations", row.name); },
		openVitalsRow(row) { this.openClinicalRecord("vitals", row.name); },
		handleConsultationRowAction({ row }) { this.openConsultationRow(row); },
		handleVitalsRowAction({ row }) { this.openVitalsRow(row); },
		openClinicalRecord(tab, name) { this.tab = tab; this.mode = "form"; this.updateRoute({ tab, name }); this.loadCurrentRoute(); },
		backToList() { this.navigateWithDirtyGuard(() => { this.mode = "list"; this.resetDocumentState(); this.updateRoute({ tab: this.tab }); this.loadCurrentRoute(); }); },
		resetDocumentState() { this.document = {}; this.model = {}; this.originalModel = "{}"; this.dirty = false; this.fieldErrors = {}; },
		onModelUpdate(next) { this.model = clone(next); this.dirty = JSON.stringify(this.model) !== this.originalModel; },
		async onDocumentChange(payload) {
			const fieldname = payload?.field?.fieldname;
			if (fieldname === "patient" && payload.value) {
				try {
					const defaults = await this.call(API.patientDefaults, { patient: payload.value });
					if (defaults) this.onModelUpdate({ ...this.model, primary_owner: defaults.primary_owner || "", service_branch: this.model.service_branch || defaults.service_branch || "" });
				} catch (error) { frappe.show_alert({ message: errorMessage(error), indicator: "orange" }); }
			}
		},
		async onSearchOption(payload) {
			const fieldname = payload?.field?.fieldname;
			const option = payload?.option || {};
			if (fieldname === "linked_appointment" && option.value) {
				const context = await this.call(API.appointmentContext, { appointment: option.value });
				if (context) this.onModelUpdate({ ...this.model, patient: context.patient || this.model.patient, service_branch: context.service_branch || this.model.service_branch, consulting_practitioner: context.consulting_practitioner || this.model.consulting_practitioner, presenting_complaint: context.presenting_complaint || this.model.presenting_complaint });
				return;
			}
			if (this.tab === "vitals" && fieldname === "consultation" && option.value) {
				this.onModelUpdate({ ...this.model, consultation: option.value, patient: option.patient || this.model.patient, service_branch: option.service_branch || this.model.service_branch });
				return;
			}
			if (fieldname === "item" && option.value && this.tab === "consultations") {
				const rows = clone(this.model.planned_treatments || []);
				let index = rows.findIndex((row) => payload.row?.name && row.name === payload.row.name);
				if (index < 0) index = rows.findIndex((row) => row.item === option.value);
				if (index < 0) return;
				const defaults = await this.call(API.treatmentDefaults, { item: option.value, company: this.model.company || null, customer: this.model.primary_owner || null, branch: this.model.service_branch || null });
				rows[index] = { ...rows[index], ...defaults, item: option.value, qty: rows[index].qty || 1, amount: Number(rows[index].qty || 1) * Number(defaults?.rate || rows[index].rate || 0) };
				this.onModelUpdate({ ...this.model, planned_treatments: rows });
			}
		},
		async saveDocument() {
			if (!this.canSave || this.saving) return;
			this.saving = true;
			this.error = "";
			try {
				const method = this.tab === "consultations" ? API.consultationSave : API.vitalsSave;
				const saved = await this.call(method, { values: normalizeModelForServer(this.model), name: this.document.name || null, modified: this.document.modified || null });
				this.document = saved || {};
				this.model = normalizeModelForInput(this.document.values || {});
				this.originalModel = JSON.stringify(this.model);
				this.dirty = false;
				this.updateRoute({ tab: this.tab, name: this.document.name });
				frappe.show_alert({ message: __("Clinical record saved."), indicator: "green" });
			} catch (error) {
				this.error = errorMessage(error, "Unable to save the clinical record.");
			} finally { this.saving = false; }
		},
		async requestTransition(transition) {
			if (this.dirty) { frappe.msgprint(__("Save or discard changes before changing the consultation status.")); return; }
			if (transition.requires_preflight || transition.status === "Cancelled") { await this.openCancellationDialog(); return; }
			frappe.confirm(__("Move this consultation to {0}?", [transition.status]), async () => {
				this.actionBusy = true;
				try {
					const response = await this.call(API.consultationTransition, { name: this.document.name, status: transition.status, modified: this.document.modified });
					this.applyReturnedDocument(response?.document);
					frappe.show_alert({ message: __("Consultation status updated."), indicator: "green" });
				} catch (error) { frappe.msgprint(errorMessage(error)); } finally { this.actionBusy = false; }
			});
		},
		async handleConsultationAction(action) {
			if (["history", "latest_vitals", "appointments"].includes(action.kind)) {
				if (action.kind === "history") { this.tab = "history"; this.mode = "history"; this.historyFilters.patient = this.model.patient; this.updateRoute({ tab: "history", patient: this.model.patient }); await this.loadHistory(false); return; }
				this.openInfoAction(action.kind);
				return;
			}
			if (action.kind === "billing") { this.openBilling(); return; }
			if (action.kind === "new_vitals") { this.openNewVitals({ patient: this.model.patient, consultation: this.document.name, service_branch: this.model.service_branch }); return; }
			if (this.dirty) { frappe.msgprint(__("Save or discard consultation changes before running this action.")); return; }
			if (action.kind === "follow_up") { this.openActionDialog({ kind: "follow_up", action: "create_follow_up", title: "Create Follow-up Appointment", confirmLabel: "Create Follow-up", values: { appointment_datetime: this.model.follow_up_date ? `${this.model.follow_up_date}T09:00` : "", notes: "" } }); return; }
			if (action.kind === "hospitalisation") { this.openActionDialog({ kind: "confirm", action: "admit_hospitalisation", title: "Admit for Hospitalisation", message: "Create a hospitalisation record from this consultation? Existing admission, occupancy and billing rules remain authoritative.", confirmLabel: "Create Admission" }); return; }
			if (action.kind === "new_lab") { await this.openOptionAction("lab"); return; }
			if (action.kind === "new_vaccination") { await this.openOptionAction("vaccination"); return; }
			if (action.kind === "dispensary") { await this.openOptionAction("dispensary"); }
		},
		openInfoAction(kind) {
			if (kind === "latest_vitals") {
				const row = this.document.related?.latest_vitals || {};
				this.openActionDialog({ kind: "info", title: "Latest Vital Signs", entries: [{ label: "Recorded On", value: this.formatDateTime(row.recorded_on) }, { label: "Weight", value: this.valueOrDash(row.weight) }, { label: "Temperature", value: this.valueOrDash(row.temperature) }, { label: "Heart Rate", value: this.valueOrDash(row.heart_rate) }, { label: "Respiratory Rate", value: this.valueOrDash(row.respiratory_rate) }, { label: "Pain Score", value: this.valueOrDash(row.pain_score) }] });
			} else {
				const summary = this.document.related?.appointments || {};
				this.openActionDialog({ kind: "info", title: "Appointment Context", entries: Object.entries(summary).map(([label, value]) => ({ label: label.replaceAll("_", " "), value })) });
			}
		},
		openBilling() {
			if (!window.vetedgeBillingModal?.open) { frappe.msgprint(__("Billing & Payment is unavailable.")); return; }
			const workspace = this;
			window.vetedgeBillingModal.open({
				doc: { doctype: "Veterinary Consultation", name: this.document.name },
				is_new() { return !workspace.document.name; },
				is_dirty() { return workspace.dirty; },
				async reload_doc() { await workspace.reloadDocument(); },
			});
		},
		async openOptionAction(kind) {
			this.actionBusy = true;
			try {
				const options = await this.call(API.actionOptions, { name: this.document.name, action: kind });
				if (kind === "lab") this.openActionDialog({ kind: "lab", action: "create_lab_order", title: "New Lab Order", confirmLabel: "Create Lab Order", options, values: { lab_tests: [], sample_notes: "" } });
				if (kind === "vaccination") this.openActionDialog({ kind: "vaccination", action: "create_vaccination", title: "New Vaccination", subtitle: options?.patient_species ? `Patient species: ${options.patient_species}` : "", confirmLabel: "Create Vaccination", options, values: { vaccine: "", dose: "", route: "", notes: "", administered_on: normalizeDateTimeForInput(frappe.datetime.now_datetime()), next_due_date: "", rate: null, create_invoice: 1, post_stock: 1 } });
				if (kind === "dispensary") this.openActionDialog({ kind: "dispensary", action: "confirm_dispensary", title: "Confirm Dispensary Issue", confirmLabel: "Confirm and Post", options, values: { dispensed_items: clone(options?.items || []) } });
			} catch (error) { frappe.msgprint(errorMessage(error)); } finally { this.actionBusy = false; }
		},
		async openCancellationDialog() {
			this.actionBusy = true;
			try {
				const options = await this.call(API.actionOptions, { name: this.document.name, action: "cancellation" });
				this.openActionDialog({ kind: "cancellation", action: "cancel", title: "Cancel Consultation", confirmLabel: "Cancel Consultation", danger: true, options, values: {} });
			} catch (error) { frappe.msgprint(errorMessage(error)); } finally { this.actionBusy = false; }
		},
		openActionDialog(config) { this.actionDialog = { open: true, kind: config.kind || "confirm", title: config.title || "Clinical action", subtitle: config.subtitle || this.document.name || "", message: config.message || "", values: clone(config.values || {}), options: clone(config.options || {}), entries: clone(config.entries || []), confirmLabel: config.confirmLabel || "Continue", danger: Boolean(config.danger), action: config.action || "" }; },
		closeActionDialog(force = false) { if (this.actionBusy && !force) return; this.actionDialog = { open: false, kind: "", title: "Clinical action", subtitle: "", message: "", values: {}, options: {}, entries: [], confirmLabel: "Continue", danger: false, action: "" }; },
		async executeActionDialog() {
			if (!this.actionFormValid || this.actionBusy) return;
			this.actionBusy = true;
			try {
				if (this.actionDialog.kind === "cancellation") {
					const response = await this.call(API.consultationTransition, { name: this.document.name, status: "Cancelled", modified: this.document.modified });
					this.applyReturnedDocument(response?.document);
				} else {
					const response = await this.call(API.consultationAction, { name: this.document.name, action: this.actionDialog.action, modified: this.document.modified, values: normalizeModelForServer(this.actionDialog.values) });
					this.applyReturnedDocument(response?.document);
					const result = response?.result || {};
					if (this.actionDialog.action === "create_lab_order" && (result.name || result.lab_order)) this.openDoc("Veterinary Lab Order", result.name || result.lab_order);
					if (this.actionDialog.action === "create_vaccination" && (result.name || result.vaccination_record)) this.openDoc("Veterinary Vaccination Record", result.name || result.vaccination_record);
					if (this.actionDialog.action === "admit_hospitalisation" && (result.name || result.hospitalisation)) this.openDoc("Veterinary Hospitalisation", result.name || result.hospitalisation);
				}
				this.closeActionDialog(true);
				frappe.show_alert({ message: __("Clinical action completed."), indicator: "green" });
			} catch (error) { frappe.msgprint(errorMessage(error)); } finally { this.actionBusy = false; }
		},
		applyReturnedDocument(document) { if (!document) return; this.document = document; this.model = normalizeModelForInput(document.values || {}); this.originalModel = JSON.stringify(this.model); this.dirty = false; },
		openCancellationResolution() { this.closeActionDialog(true); frappe.new_doc("Veterinary Consultation Cancellation Resolution", { consultation: this.document.name }); },
		async loadHistory(updateRoute = true) {
			if (!this.historyFilters.patient) return;
			this.loading = true;
			this.error = "";
			try {
				this.history = await this.call(API.history, { patient: this.historyFilters.patient, from_date: this.historyFilters.from_date || null, to_date: this.historyFilters.to_date || null, limit: 100 }) || {};
				this.historyLoaded = true;
				this.historyFilters.from_date = this.history.from_date || this.historyFilters.from_date;
				this.historyFilters.to_date = this.history.to_date || this.historyFilters.to_date;
				if (updateRoute) this.updateRoute({ tab: "history", patient: this.historyFilters.patient, from_date: this.historyFilters.from_date, to_date: this.historyFilters.to_date });
			} catch (error) { this.error = errorMessage(error, "Unable to load medical history."); } finally { this.loading = false; }
		},
		setHistoryPatient(value) { this.historyFilters.patient = value || ""; this.historyLoaded = false; this.history = {}; },
		openHistoryConsultation({ row }) { this.openClinicalRecord("consultations", row.name); },
		async linkSearch(field, query, values = this.model) { return this.call(API.link, { context: this.tab === "consultations" ? "consultation" : "vitals", fieldname: field.fieldname, query, values: normalizeModelForServer(values), child_doctype: null }); },
		async childLinkSearch(field, query) { return this.call(API.link, { context: "consultation", fieldname: field.fieldname, query, values: normalizeModelForServer(this.model), child_doctype: field.options === "Veterinary Symptom" ? "Consultation Symptom" : field.options === "Veterinary Diagnosis" ? "Consultation Diagnosis" : "Planned Treatment Item" }); },
		async filterLinkSearch(fieldname, query) { return this.call(API.link, { context: this.tab === "vitals" ? "vitals" : "consultation", fieldname, query, values: { patient: this.filters.patient, service_branch: this.filters.branch }, child_doctype: null }); },
		setFilter(fieldname, value) { this.filters[fieldname] = value || ""; },
		async applyFilters() { if (this.tab === "consultations") this.consultationList.start = 0; else this.vitalsList.start = 0; this.loading = true; try { await Promise.all([this.loadSummary(), this.loadList()]); } catch (error) { this.error = errorMessage(error); } finally { this.loading = false; } },
		async resetFilters() { this.filters = { search: "", status: "", branch: "", practitioner: "", patient: "", consultation: "" }; await this.applyFilters(); },
		hasPrevious(list) { return (list.start || 0) > 0; },
		hasNext(list) { return (list.start || 0) + (list.rows?.length || 0) < (list.total || 0); },
		firstVisible(list) { return list.total ? (list.start || 0) + 1 : 0; },
		lastVisible(list) { return Math.min((list.start || 0) + (list.rows?.length || 0), list.total || 0); },
		async previousPage() { const list = this.tab === "consultations" ? this.consultationList : this.vitalsList; list.start = Math.max((list.start || 0) - this.pageLength, 0); await this.applyFiltersWithoutReset(); },
		async nextPage() { const list = this.tab === "consultations" ? this.consultationList : this.vitalsList; list.start = (list.start || 0) + this.pageLength; await this.applyFiltersWithoutReset(); },
		async applyFiltersWithoutReset() { this.loading = true; try { await this.loadList(); } catch (error) { this.error = errorMessage(error); } finally { this.loading = false; } },
		formatDateTime(value) { if (!value) return "—"; return frappe.datetime?.str_to_user ? frappe.datetime.str_to_user(value) : String(value); },
		valueOrDash(value) { return value === null || value === undefined || value === "" ? "—" : value; },
		openDoc(doctype, name) { if (!name) return; frappe.set_route("Form", doctype, name); },
		openRoute(route) { if (!route) return; window.location.href = route; },
		updateRoute(params) {
			const query = new URLSearchParams();
			for (const [key, value] of Object.entries(params || {})) if (value !== undefined && value !== null && value !== "") query.set(key, value);
			const next = `/app/vetedge-clinical-workspace${query.toString() ? `?${query.toString()}` : ""}`;
			window.history.pushState({}, "", next);
		},
		handleBrowserNavigation() { this.loadCurrentRoute(); },
		handleBeforeUnload(event) { if (!this.dirty) return; event.preventDefault(); event.returnValue = ""; },
		navigateWithDirtyGuard(handler) { if (!this.dirty) { handler(); return; } frappe.confirm(__("Discard unsaved clinical changes?"), handler); },
	},
};
