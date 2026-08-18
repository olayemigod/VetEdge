<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/desk/vetedge-clinical-workspace"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Clinical Operations"
					:title="detail.open ? detailTitle : 'Veterinary Clinical Workspace'"
					:subtitle="detail.open ? detailSubtitle : 'Capture consultations, clinical findings, treatment plans, vitals and safe workflow transitions.'"
					:action-label="detail.open ? 'Back to Consultations' : 'New Consultation'"
					@action="detail.open ? backToList() : startNewConsultation()"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar v-if="!detail.open" title="Filter consultations">
					<div class="clinical-filter-grid">
						<EdgeLinkField :model-value="filters.branch" label="Branch" placeholder="All permitted branches" :searcher="(query) => linkSearch('branch', query)" @update:model-value="(value) => setFilter('branch', value)" />
						<EdgeLinkField :model-value="filters.practitioner" label="Practitioner" placeholder="All permitted doctors" :searcher="(query) => contextSearch('practitioner', query)" @update:model-value="(value) => setFilter('practitioner', value)" />
						<EdgeDropdown :model-value="filters.status" label="Status" placeholder="All statuses" :options="statusOptions" @update:model-value="(value) => setFilter('status', value)" />
						<EdgeInput v-model="filters.search" type="search" label="Search" placeholder="Consultation, patient, owner or complaint" @keyup.enter="applyFilters" />
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<template v-if="!detail.open">
				<section class="clinical-summary" aria-label="Consultation summary">
					<EdgeStatCard label="Draft" :value="summary.draft || 0" icon="clipboard" />
					<EdgeStatCard label="In progress" :value="summary.in_progress || 0" icon="stethoscope" />
					<EdgeStatCard label="Awaiting payment" :value="summary.awaiting_payment || 0" icon="wallet" />
					<EdgeStatCard label="Ready for treatment" :value="summary.ready_for_treatment || 0" icon="clipboard" />
					<EdgeStatCard label="Completed" :value="summary.completed || 0" icon="check" />
				</section>
				<EdgeLoadingState v-if="loading" message="Loading consultations..." :skeleton="true" />
				<EdgeErrorState v-else-if="error" title="Consultations could not load" :message="error" action-label="Try again" @retry="refreshList" />
				<EdgeDataTable v-else :columns="listColumns" :rows="consultations.rows || []" empty-title="No consultations" empty-description="No consultations match the current filters." @row-click="openConsultation">
					<template #footer>
						<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ consultations.total || 0 }}</span>
						<div class="clinical-row-actions">
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext" @click="nextPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>

			<template v-else>
				<EdgeLoadingState v-if="detail.loading" message="Loading consultation..." :skeleton="true" />
				<EdgeErrorState v-else-if="detail.error" title="Consultation could not load" :message="detail.error" action-label="Back to list" @retry="backToList" />
				<div v-else class="clinical-detail">
					<section class="clinical-statusbar">
						<div class="clinical-context-badges">
							<EdgeStatusBadge :label="detail.status || 'Draft'" :status="detail.status || 'Draft'" />
							<span>Payment: <strong>{{ form.payment_status || 'Not Billed' }}</strong></span>
							<span>Dispensary: <strong>{{ form.dispensary_status || 'Not Required' }}</strong></span>
						</div>
						<div class="clinical-row-actions">
							<button v-if="dispensaryPending" type="button" class="edge-button" :disabled="busy || isNew" @click="openDispensary">Review Dispensary</button>
							<button type="button" class="edge-button" :disabled="busy || isNew || !detail.capabilities.view_history" @click="openHistory">Medical History</button>
							<button type="button" class="edge-button" :disabled="busy || isNew || !detail.capabilities.create_vitals" @click="openVitals">New Vitals</button>
							<button type="button" class="edge-button" :disabled="busy || isNew || !detail.capabilities.open_billing" @click="openBilling">Billing & Payment</button>
							<button type="button" class="edge-button edge-button--primary" :disabled="busy || !detail.can_write" @click="saveConsultation">{{ busy ? 'Saving…' : 'Save Consultation' }}</button>
						</div>
					</section>

					<nav class="clinical-tabs" aria-label="Consultation sections">
						<button v-for="tab in tabs" :key="tab.value" type="button" :class="['clinical-tab', { 'is-active': activeTab === tab.value }]" @click="activeTab = tab.value">
							<span>{{ tab.label }}</span><small>{{ tab.description }}</small>
						</button>
					</nav>

					<section v-if="activeTab === 'visit'" class="clinical-panel">
						<h3>Patient and Visit</h3>
						<div class="clinical-grid">
							<EdgeLinkField :model-value="form.patient" :selected-label="form.patient_label" label="Patient" placeholder="Select patient" :disabled="identityLocked" :searcher="(query) => linkSearch('patient', query)" @update:model-value="selectPatient" />
							<EdgeInput :model-value="form.primary_owner_label || form.primary_owner || ''" label="Pet Owner" readonly description="Derived from the selected Veterinary Patient." />
							<EdgeLinkField :model-value="form.service_branch" label="Service Branch" placeholder="Select branch" :disabled="identityLocked" :searcher="(query) => linkSearch('branch', query)" @update:model-value="(value) => updateField('service_branch', value)" />
							<EdgeLinkField :model-value="form.consulting_practitioner" label="Consulting Practitioner" placeholder="Select doctor" :searcher="(query) => contextSearch('practitioner', query)" @update:model-value="(value) => updateField('consulting_practitioner', value)" />
							<EdgeLinkField :model-value="form.consultation_type" label="Consultation Type" placeholder="Select consultation type" :searcher="(query) => contextSearch('consultation_type', query)" @update:model-value="(value) => updateField('consultation_type', value)" />
							<EdgeInput :model-value="form.consultation_datetime" type="datetime-local" label="Consultation Date/Time" @update:model-value="(value) => updateField('consultation_datetime', value)" />
							<EdgeTextarea class="clinical-wide" :model-value="form.presenting_complaint" label="Presenting Complaint" :rows="4" @update:model-value="(value) => updateField('presenting_complaint', value)" />
						</div>
						<div v-if="!isNew" class="clinical-row-actions">
							<button type="button" class="edge-button edge-button--compact" @click="openRelated('Veterinary Lab Order')">Laboratory Orders</button>
							<button type="button" class="edge-button edge-button--compact" @click="openRelated('Veterinary Vaccination Record')">Vaccinations</button>
							<button type="button" class="edge-button edge-button--compact" @click="openRelated('Veterinary Hospitalisation')">Hospitalisation</button>
						</div>
					</section>

					<section v-if="activeTab === 'clinical'" class="clinical-panel">
						<h3>Clinical Findings</h3>
						<EdgeTextarea :model-value="form.examination_notes" label="Examination Notes" :rows="5" @update:model-value="(value) => updateField('examination_notes', value)" />
						<EdgeTextarea :model-value="form.assessment_notes" label="Assessment Notes" :rows="5" @update:model-value="(value) => updateField('assessment_notes', value)" />
						<header class="clinical-subhead"><div><h4>Symptoms</h4><p>Capture active and clinically relevant symptoms.</p></div><button type="button" class="edge-button edge-button--compact" :disabled="!detail.can_write" @click="addSymptom">Add Symptom</button></header>
						<div v-for="(row, index) in form.symptoms" :key="row._key || row.name || index" class="clinical-child-row">
							<EdgeLinkField :model-value="row.symptom" label="Symptom" placeholder="Select symptom" :searcher="(query) => linkSearch('symptom', query)" @update:model-value="(value) => updateChild('symptoms', index, 'symptom', value)" />
							<EdgeInput :model-value="row.notes" label="Notes" @update:model-value="(value) => updateChild('symptoms', index, 'notes', value)" />
							<button type="button" class="edge-button edge-button--danger edge-button--compact" @click="removeChild('symptoms', index)">Remove</button>
						</div>
						<header class="clinical-subhead"><div><h4>Diagnoses</h4><p>Diagnosis and treatment capture remains permission-aware.</p></div><button type="button" class="edge-button edge-button--compact" :disabled="!detail.can_write" @click="addDiagnosis">Add Diagnosis</button></header>
						<div v-for="(row, index) in form.diagnoses" :key="row._key || row.name || index" class="clinical-child-row clinical-child-row--diagnosis">
							<EdgeLinkField :model-value="row.diagnosis" label="Diagnosis" placeholder="Select diagnosis" :searcher="(query) => linkSearch('diagnosis', query)" @update:model-value="(value) => updateChild('diagnoses', index, 'diagnosis', value)" />
							<EdgeDropdown :model-value="row.diagnosis_type" label="Diagnosis Type" placeholder="Select type" :options="diagnosisTypeOptions" @update:model-value="(value) => updateChild('diagnoses', index, 'diagnosis_type', value)" />
							<EdgeInput :model-value="row.notes" label="Notes" @update:model-value="(value) => updateChild('diagnoses', index, 'notes', value)" />
							<button type="button" class="edge-button edge-button--danger edge-button--compact" @click="removeChild('diagnoses', index)">Remove</button>
						</div>
					</section>

					<section v-if="activeTab === 'treatment'" class="clinical-panel">
						<header class="clinical-subhead"><div><h3>Treatment Plan</h3><p v-if="detail.scope_locked">Treatment scope is locked because this consultation is {{ detail.status }}.</p><p v-else>Add treatment rows before the consultation reaches Ready for Treatment.</p></div><button type="button" class="edge-button edge-button--compact" :disabled="detail.scope_locked || !detail.can_write" @click="addTreatment">Add Treatment</button></header>
						<EdgeTextarea :model-value="form.treatment_plan_summary" label="Treatment Plan Summary" :rows="4" @update:model-value="(value) => updateField('treatment_plan_summary', value)" />
						<div v-for="(row, index) in form.planned_treatments" :key="row._key || row.name || index" class="clinical-treatment-row">
							<EdgeLinkField :model-value="row.item" label="Treatment Item" placeholder="Select treatment item" :disabled="treatmentFieldLocked(row, 'item')" :searcher="(query) => linkSearch('treatment_item', query)" @update:model-value="(value) => updateTreatmentItem(index, value)" />
							<EdgeInput :model-value="row.description" label="Description" :disabled="treatmentFieldLocked(row, 'description')" @update:model-value="(value) => updateChild('planned_treatments', index, 'description', value)" />
							<EdgeInput :model-value="row.qty" type="number" label="Qty" min="0.001" step="0.001" :disabled="treatmentFieldLocked(row, 'qty')" @update:model-value="(value) => updateChild('planned_treatments', index, 'qty', value)" />
							<EdgeInput :model-value="row.rate" type="number" label="Rate" min="0" step="0.01" :disabled="treatmentFieldLocked(row, 'rate')" @update:model-value="(value) => updateChild('planned_treatments', index, 'rate', value)" />
							<div class="clinical-treatment-meta"><EdgeStatusBadge :label="row.billing_status || 'Pending'" :status="row.billing_status || 'Pending'" /><span>{{ row.payment_status || 'Not Billed' }}</span><strong>{{ formatMoney((Number(row.qty) || 0) * (Number(row.rate) || 0)) }}</strong></div>
							<button type="button" class="edge-button edge-button--danger edge-button--compact" :disabled="treatmentRemovalLocked(row)" @click="removeChild('planned_treatments', index)">Remove</button>
						</div>
						<EdgeInput :model-value="form.follow_up_date" type="datetime-local" label="Follow-up Date/Time" @update:model-value="(value) => updateField('follow_up_date', value)" />
					</section>

					<section v-if="activeTab === 'vitals'" class="clinical-panel">
						<h3>Latest Vitals and Billing Context</h3>
						<div v-if="detail.latest_vitals" class="clinical-vitals"><div v-for="entry in vitalEntries" :key="entry.label"><span>{{ entry.label }}</span><strong>{{ entry.value || '—' }}</strong></div></div>
						<div v-else class="clinical-empty">No vitals have been recorded for this consultation.</div>
						<div class="clinical-invoices"><h4>Consultation Invoices</h4><div v-if="!(form.consultation_invoices || []).length" class="clinical-empty">No consultation invoice references yet.</div><button v-for="invoice in form.consultation_invoices || []" :key="invoice.invoice || invoice.name" type="button" class="edge-button edge-button--compact" @click="openDocument('Sales Invoice', invoice.invoice || invoice.name)">{{ invoice.invoice || invoice.name }} · {{ invoice.payment_status || invoice.status || 'Open' }}</button></div>
					</section>

					<section v-if="!isNew && (detail.actions || []).length" class="clinical-workflow"><div><h3>Workflow Actions</h3><p>Transitions use existing consultation payment, dispensary, cancellation and completion gates.</p></div><div class="clinical-row-actions"><button v-for="action in detail.actions" :key="action.key" type="button" :class="['edge-button', action.danger ? 'edge-button--danger' : action.primary ? 'edge-button--primary' : '']" :disabled="busy" @click="runAction(action)">{{ action.label }}</button></div></section>
				</div>
			</template>
		</EdgePageLayout>

		<EdgeModal :open="vitalsDialog.open" title="Record Veterinary Vitals" subtitle="Vitals remain separate clinical records linked to this consultation." :busy="busy" @close="closeVitals">
			<div class="clinical-grid">
				<EdgeInput v-for="field in vitalFields" :key="field.name" :model-value="vitalsDialog.values[field.name]" :label="field.label" :type="field.type || 'text'" :min="field.min" :step="field.step" @update:model-value="(value) => setVital(field.name, value)" />
				<EdgeTextarea class="clinical-wide" :model-value="vitalsDialog.values.notes" label="Notes" :rows="4" @update:model-value="(value) => setVital('notes', value)" />
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeVitals">Cancel</button><button type="button" class="edge-button edge-button--primary" :disabled="busy" @click="saveVitals">Save Vitals</button></template>
		</EdgeModal>

		<EdgeModal :open="historyDialog.open" title="Patient Medical History" :subtitle="historySubtitle" :busy="historyDialog.loading" @close="closeHistory">
			<EdgeLoadingState v-if="historyDialog.loading" message="Loading medical history..." :skeleton="true" />
			<div v-else class="clinical-history"><section v-for="section in historySections" :key="section.label"><h4>{{ section.label }}</h4><div v-if="!section.rows.length" class="clinical-empty">No records.</div><article v-for="row in section.rows" :key="row.name || row.timestamp"><strong>{{ row.title || row.name || row.vaccine || row.tests_summary || 'Clinical record' }}</strong><span>{{ row.status || row.payment_status || '' }}</span><p>{{ row.presenting_complaint || row.assessment_notes || row.results_summary || row.notes || '' }}</p></article></section></div>
			<template #footer><button type="button" class="edge-button" @click="closeHistory">Close</button></template>
		</EdgeModal>

		<EdgeModal :open="dispensaryDialog.open" title="Review Dispensary Issue" :subtitle="dispensarySubtitle" :busy="dispensaryDialog.loading || busy" @close="closeDispensary">
			<EdgeLoadingState v-if="dispensaryDialog.loading" message="Loading dispensary context..." :skeleton="true" />
			<div v-else class="clinical-dispensary">
				<section class="clinical-dispensary-meta"><span>Warehouse</span><strong>{{ dispensaryDialog.context.warehouse || 'Not configured' }}</strong><span>Status</span><strong>{{ dispensaryDialog.context.status || 'Not Required' }}</strong></section>
				<p>{{ dispensaryDialog.context.guidance || '' }}</p>
				<div v-if="!(dispensaryDialog.items || []).length" class="clinical-empty">No dispensary items are pending.</div>
				<div v-for="(row, index) in dispensaryDialog.items || []" :key="row.planned_treatment_row || `${row.item}-${index}`" class="clinical-dispensary-row">
					<div><strong>{{ row.item_name || row.item }}</strong><small>{{ row.uom || '' }}</small></div>
					<EdgeInput :model-value="row.planned_qty" type="number" label="Planned Qty" readonly />
					<EdgeInput :model-value="row.dispensed_qty" type="number" label="Dispensed Qty" min="0" step="0.001" :disabled="!dispensaryDialog.context.can_confirm" @update:model-value="(value) => updateDispensaryQty(index, value)" />
					<EdgeInput :model-value="row.selected_batch || ''" label="Batch" readonly />
				</div>
			</div>
			<template #footer><button type="button" class="edge-button" :disabled="busy" @click="closeDispensary">Close</button><button v-if="dispensaryDialog.context.can_confirm && dispensaryPending" type="button" class="edge-button edge-button--primary" :disabled="busy || dispensaryDialog.loading" @click="confirmDispensary">Confirm Dispensary Issue</button></template>
		</EdgeModal>

		<EdgeModal :open="confirmation.open" :title="confirmation.title" :subtitle="confirmation.subtitle" :busy="false" @close="cancelConfirmation">
			<p>{{ confirmation.message }}</p>
			<template #footer><button type="button" class="edge-button" @click="cancelConfirmation">Keep Editing</button><button type="button" :class="['edge-button', confirmation.danger ? 'edge-button--danger' : 'edge-button--primary']" @click="confirmConfirmation">{{ confirmation.confirmLabel }}</button></template>
		</EdgeModal>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	summary: "vetedge.services.clinical_workspace.get_clinical_summary",
	list: "vetedge.services.clinical_workspace.get_consultations",
	detail: "vetedge.services.clinical_workspace.get_consultation_detail",
	save: "vetedge.services.clinical_workspace_stage3.save_consultation",
	action: "vetedge.services.clinical_workspace.perform_consultation_action",
	vitals: "vetedge.services.clinical_workspace.create_consultation_vitals",
	history: "vetedge.services.clinical_workspace.get_consultation_history",
	links: "vetedge.services.clinical_workspace.get_clinical_link_options",
	contextLinks: "vetedge.services.clinical_workspace_context.get_clinical_context_options",
	patientContext: "vetedge.services.clinical_workspace_context.get_patient_owner_context",
	defaults: "vetedge.services.clinical_workspace.get_treatment_defaults",
	feePolicy: "vetedge.services.clinical_workspace_stage3.get_default_consultation_fee_policy",
	treatmentOrder: "vetedge.services.clinical_workspace_phase5.get_treatment_display_order",
	dispensaryContext: "vetedge.services.clinical_workspace_phase5.get_dispensary_workspace_context",
	confirmDispensary: "vetedge.services.clinical_workspace_phase5.confirm_workspace_dispensary",
});
const STATUSES = ["Draft", "In Progress", "Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled"];
const DIAGNOSIS_TYPES = ["Primary", "Differential", "Rule Out", "Resolved"];
const blankCapabilities = () => ({ create_vitals: false, view_history: false, open_billing: false });
const blankDetail = (overrides = {}) => ({ open: false, loading: false, error: "", name: "", modified: "", status: "Draft", can_write: true, scope_locked: false, latest_vitals: null, actions: [], capabilities: blankCapabilities(), ...overrides });
const blankForm = () => ({ patient: "", patient_label: "", primary_owner: "", primary_owner_label: "", consultation_datetime: "", consultation_type: "General Consultation", service_branch: "", consulting_practitioner: "", linked_appointment: "", presenting_complaint: "", examination_notes: "", assessment_notes: "", treatment_plan_summary: "", follow_up_date: "", symptoms: [], diagnoses: [], planned_treatments: [], consultation_invoices: [], payment_status: "Not Billed", dispensary_status: "Not Required" });
const blankConfirmation = () => ({ open: false, title: "", subtitle: "", message: "", confirmLabel: "Continue", danger: false, resolve: null });
const blankDispensary = () => ({ open: false, loading: false, context: {}, items: [] });
function call(method, args = {}) { return frappe.call({ method, args }).then((response) => response.message); }
function message(error, fallback) { return error?.message || error?._server_messages || error?.exc_type || fallback; }
function localDatetime(value) { return value ? String(value).replace(" ", "T").slice(0, 16) : ""; }
function serverDatetime(value) { return value ? String(value).replace("T", " ") : value; }
function rowKey(row) { return row?.name || window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`; }

export default {
	name: "VetEdgeClinicalWorkspace",
	data() {
		return {
			identity: window.frappe?.boot?.vetedge_ui_identity || {},
			statuses: STATUSES,
			tabs: [
				{ value: "visit", label: "Visit", description: "Patient and consultation context" },
				{ value: "clinical", label: "Clinical Findings", description: "Complaint, examination and diagnosis" },
				{ value: "treatment", label: "Treatment Plan", description: "Billing-aware planned treatment" },
				{ value: "vitals", label: "Vitals & Billing", description: "Latest observations and invoice links" },
			],
			activeTab: "visit",
			summary: {},
			consultations: { rows: [], total: 0, start: 0, page_length: 25 },
			filters: { branch: "", practitioner: "", status: "", search: "" },
			loading: false,
			error: "",
			busy: false,
			dirty: false,
			detail: blankDetail(),
			form: blankForm(),
			feePolicy: {
				allow_editing_default_consultation_fee: false,
				allow_editing_lab_billing: false,
				allow_editing_vaccination_billing: false,
				default_consultation_source_detail: "Default Consultation Fee",
			},
			vitalsDialog: { open: false, values: {} },
			historyDialog: { open: false, loading: false, data: {} },
			dispensaryDialog: blankDispensary(),
			confirmation: blankConfirmation(),
			listColumns: [
				{ key: "consultation_datetime", label: "Date/Time", type: "datetime" },
				{ key: "patient_label", label: "Patient" },
				{ key: "consultation_type", label: "Consultation Type" },
				{ key: "consulting_practitioner_name", label: "Practitioner" },
				{ key: "service_branch", label: "Branch" },
				{ key: "status", label: "Status", type: "status" },
				{ key: "payment_status", label: "Payment", type: "status" },
			],
			vitalFields: [
				{ name: "temperature", label: "Temperature", type: "number", min: 0, step: "0.1" },
				{ name: "weight", label: "Weight", type: "number", min: 0, step: "0.01" },
				{ name: "heart_rate", label: "Heart Rate", type: "number", min: 0, step: "1" },
				{ name: "respiratory_rate", label: "Respiratory Rate", type: "number", min: 0, step: "1" },
				{ name: "body_condition_score", label: "Body Condition Score", type: "number", min: 0, step: "0.5" },
				{ name: "pain_score", label: "Pain Score", type: "number", min: 0, step: "1" },
			],
		};
	},
	computed: {
		statusOptions() { return this.statuses.map((value) => ({ value, label: value })); },
		diagnosisTypeOptions() { return DIAGNOSIS_TYPES.map((value) => ({ value, label: value })); },
		userName() { return window.frappe?.session?.user_fullname || window.frappe?.session?.user || ""; },
		branchName() { return this.form.service_branch || this.filters.branch || ""; },
		isNew() { return !this.detail.name; },
		identityLocked() { return !this.isNew && this.detail.status !== "Draft"; },
		detailTitle() { return this.form.consultation_title || this.detail.name || "New Veterinary Consultation"; },
		detailSubtitle() { return [this.form.patient_label || this.form.patient, this.form.consulting_practitioner_name, this.form.service_branch].filter(Boolean).join(" · ") || "Clinical consultation capture"; },
		firstVisible() { return this.consultations.total ? this.consultations.start + 1 : 0; },
		lastVisible() { return Math.min(this.consultations.start + (this.consultations.rows || []).length, this.consultations.total || 0); },
		hasPrevious() { return this.consultations.start > 0; },
		hasNext() { return this.consultations.start + this.consultations.page_length < this.consultations.total; },
		dispensaryPending() { return (this.form.dispensary_status || "") === "Pending Dispensary"; },
		dispensarySubtitle() { return [this.form.patient_label || this.form.patient, this.dispensaryDialog.context.warehouse].filter(Boolean).join(" · ") || this.detail.name; },
		vitalEntries() {
			const v = this.detail.latest_vitals || {};
			return [
				["Recorded On", frappe.datetime?.str_to_user?.(v.recorded_on) || v.recorded_on],
				["Temperature", v.temperature], ["Weight", v.weight], ["Heart Rate", v.heart_rate],
				["Respiratory Rate", v.respiratory_rate], ["Body Condition", v.body_condition_score],
				["Hydration", v.hydration_status], ["Pain Score", v.pain_score], ["Appetite", v.appetite_status],
			].map(([label, value]) => ({ label, value }));
		},
		historySubtitle() { return this.historyDialog.data?.summary?.patient_name || this.form.patient_label || this.form.patient || "Patient"; },
		historySections() {
			const data = this.historyDialog.data || {};
			return [
				{ label: "Consultations", rows: data.consultations || [] },
				{ label: "Vaccinations", rows: data.vaccinations || [] },
				{ label: "Laboratory", rows: data.labs || [] },
				{ label: "Vitals", rows: data.vitals || [] },
			];
		},
	},
	async mounted() {
		window.addEventListener("beforeunload", this.handleBeforeUnload);
		await this.loadFeePolicy();
		const params = new URLSearchParams(window.location.search || "");
		if (params.get("consultation")) return this.loadDetail(params.get("consultation"));
		if (params.has("new")) return this.startNewConsultation();
		this.refreshList();
	},
	beforeUnmount() {
		window.removeEventListener("beforeunload", this.handleBeforeUnload);
		if (this.confirmation.resolve) this.confirmation.resolve(false);
	},
	methods: {
		handleBeforeUnload(event) { if (!this.dirty) return; event.preventDefault(); event.returnValue = ""; },
		confirmDiscard() {
			if (!this.dirty) return Promise.resolve(true);
			return new Promise((resolve) => {
				this.confirmation = {
					open: true,
					title: __("Discard unsaved changes?"),
					subtitle: __("Clinical Workspace"),
					message: __("You have unsaved consultation changes. Continue without saving them?"),
					confirmLabel: __("Discard Changes"),
					danger: true,
					resolve,
				};
			});
		},
		cancelConfirmation() {
			const resolve = this.confirmation.resolve;
			this.confirmation = blankConfirmation();
			resolve?.(false);
		},
		confirmConfirmation() {
			const resolve = this.confirmation.resolve;
			this.confirmation = blankConfirmation();
			this.dirty = false;
			resolve?.(true);
		},
		async loadFeePolicy() {
			try { this.feePolicy = { ...this.feePolicy, ...(await call(API.feePolicy) || {}) }; }
			catch (_error) {}
		},
		async refreshList() {
			this.loading = true; this.error = "";
			try {
				const [summary, consultations] = await Promise.all([
					call(API.summary, { branch: this.filters.branch || undefined }),
					call(API.list, { ...this.filters, start: this.consultations.start || 0, page_length: this.consultations.page_length || 25 }),
				]);
				this.summary = summary || {};
				this.consultations = consultations || { rows: [], total: 0, start: 0, page_length: 25 };
			} catch (error) { this.error = message(error, "Unable to load consultations."); }
			finally { this.loading = false; }
		},
		applyFilters() { this.consultations.start = 0; return this.refreshList(); },
		resetFilters() { this.filters = { branch: "", practitioner: "", status: "", search: "" }; this.consultations.start = 0; return this.refreshList(); },
		setFilter(field, value) { this.filters[field] = value || ""; },
		previousPage() { this.consultations.start = Math.max(0, this.consultations.start - this.consultations.page_length); this.refreshList(); },
		nextPage() { this.consultations.start += this.consultations.page_length; this.refreshList(); },
		openConsultation(row) { return this.loadDetail(row.name); },
		async loadDetail(name) {
			if (!(await this.confirmDiscard())) return;
			this.detail = blankDetail({ open: true, loading: true, name, can_write: false });
			this.activeTab = "visit";
			try {
				this.applyDetail(await call(API.detail, { name }));
				await this.applyTreatmentOrder();
				window.history.replaceState({}, "", `/desk/vetedge-clinical-workspace?consultation=${encodeURIComponent(name)}`);
			} catch (error) { this.detail.loading = false; this.detail.error = message(error, "Unable to load consultation."); }
		},
		applyDetail(payload) {
			const values = payload?.values || {};
			this.detail = blankDetail({ open: true, name: payload?.name || "", modified: payload?.modified || "", status: payload?.status || "Draft", can_write: payload?.can_write !== false, scope_locked: Boolean(payload?.scope_locked), latest_vitals: payload?.latest_vitals || null, actions: payload?.actions || [], capabilities: { ...blankCapabilities(), ...(payload?.capabilities || {}) } });
			this.form = {
				...blankForm(), ...values,
				patient_label: values.patient_label || payload?.patient_label || values.patient || "",
				primary_owner_label: values.primary_owner_label || payload?.values?.primary_owner_label || payload?.owner_label || values.primary_owner || "",
				consultation_datetime: localDatetime(values.consultation_datetime),
				follow_up_date: localDatetime(values.follow_up_date),
				symptoms: (values.symptoms || []).map((row) => ({ ...row, _key: rowKey(row) })),
				diagnoses: (values.diagnoses || []).map((row) => ({ ...row, _key: rowKey(row) })),
				planned_treatments: (values.planned_treatments || []).map((row) => ({ ...row, _key: rowKey(row) })),
			};
			this.dirty = false;
		},
		async applyTreatmentOrder() {
			if (!this.detail.name || !(this.form.planned_treatments || []).length) return;
			try {
				const payload = await call(API.treatmentOrder, { consultation: this.detail.name });
				const order = new Map((payload?.order || []).map((name, index) => [String(name), index]));
				this.form.planned_treatments = [...this.form.planned_treatments].sort((left, right) => {
					const leftIndex = order.has(String(left.name)) ? order.get(String(left.name)) : Number.MAX_SAFE_INTEGER;
					const rightIndex = order.has(String(right.name)) ? order.get(String(right.name)) : Number.MAX_SAFE_INTEGER;
					return leftIndex - rightIndex;
				});
			} catch (_error) {}
		},
		async startNewConsultation() {
			if (!(await this.confirmDiscard())) return;
			this.detail = blankDetail({ open: true, can_write: true });
			this.form = blankForm(); this.activeTab = "visit"; this.dirty = false;
			try {
				const doctors = await this.contextSearch("practitioner", "");
				if (doctors.length === 1) this.form.consulting_practitioner = doctors[0].value;
			} catch (_error) {}
			window.history.replaceState({}, "", "/desk/vetedge-clinical-workspace?new=1");
		},
		async backToList() {
			if (!(await this.confirmDiscard())) return;
			this.detail = blankDetail(); this.form = blankForm(); this.dirty = false;
			window.history.replaceState({}, "", "/desk/vetedge-clinical-workspace"); this.refreshList();
		},
		markDirty() { this.dirty = true; },
		updateField(field, value) { this.form[field] = value ?? ""; this.markDirty(); },
		async selectPatient(value) {
			this.updateField("patient", value);
			this.form.patient_label = "";
			this.form.primary_owner = ""; this.form.primary_owner_label = "";
			if (!value) return;
			try {
				const context = await call(API.patientContext, { patient: value });
				if (this.form.patient !== value) return;
				this.form.patient_label = context?.patient?.label || context?.patient?.name || value;
				this.form.primary_owner = context?.owner?.name || "";
				this.form.primary_owner_label = context?.owner?.label || context?.owner?.name || "";
				if (!this.form.service_branch && context?.patient?.default_branch) this.form.service_branch = context.patient.default_branch;
			} catch (error) { this.error = message(error, __("Patient ownership context could not be loaded.")); }
		},
		updateChild(table, index, field, value) {
			const row = this.form?.[table]?.[index];
			if (table === 'planned_treatments' && ['Lab Order', 'Vaccination'].includes(row?.source_type) && field !== 'rate') return;
			if (table === 'planned_treatments' && ['Lab Order', 'Vaccination'].includes(row?.source_type) && !this.sourceTreatmentRateEditable(row)) return;
			this.form[table][index][field] = value ?? "";
			this.markDirty();
		},
		addSymptom() { this.form.symptoms.push({ _key: rowKey(), symptom: "", notes: "" }); this.markDirty(); },
		addDiagnosis() { this.form.diagnoses.push({ _key: rowKey(), diagnosis: "", diagnosis_type: "", notes: "" }); this.markDirty(); },
		addTreatment() { this.form.planned_treatments.push({ _key: rowKey(), item: "", description: "", qty: 1, rate: 0, billing_status: "Pending", payment_status: "Not Billed" }); this.markDirty(); },
		removeChild(table, index) {
			const row = this.form?.[table]?.[index];
			if (table === 'planned_treatments' && ['Lab Order', 'Vaccination'].includes(row?.source_type)) {
				frappe.show_alert({ message: __("Delete the source Lab Order or Vaccination from its related-record popup so the Treatment Plan and draft billing remain aligned."), indicator: 'orange' });
				return;
			}
			this.form[table].splice(index, 1); this.markDirty();
		},
		async updateTreatmentItem(index, item) {
			const row = this.form.planned_treatments[index];
			if (['Lab Order', 'Vaccination'].includes(row?.source_type)) {
				frappe.show_alert({ message: __("The ERPNext Item for Lab/Vaccination rows is fixed by its clinical master. Edit only the Rate here."), indicator: 'orange' });
				return;
			}
			row.item = item || ""; this.markDirty(); if (!item) return;
			try {
				const defaults = await call(API.defaults, { item, company: this.form.company, customer: this.form.primary_owner, branch: this.form.service_branch });
				Object.assign(row, { uom: defaults?.uom || row.uom, rate: defaults?.rate ?? row.rate, service_type: defaults?.service_type || row.service_type, treatment_type: defaults?.treatment_type || row.treatment_type });
			} catch (error) { frappe.show_alert({ message: message(error, "Treatment defaults could not load."), indicator: "orange" }); }
		},
		isDefaultConsultationFee(row) {
			return row?.source_type === "Consultation" && row?.source_detail_name === this.feePolicy.default_consultation_source_detail;
		},
		sourceTreatmentRateEditable(row) {
			if (this.detail.scope_locked || !this.detail.can_write) return false;
			if (!["", "Pending", "Draft Invoiced"].includes(row?.billing_status || "")) return false;
			if (["Paid", "Partly Paid", "Cancelled"].includes(row?.payment_status || "Not Billed")) return false;
			if (row?.source_type === "Lab Order") return Boolean(this.feePolicy.allow_editing_lab_billing);
			if (row?.source_type === "Vaccination") return Boolean(this.feePolicy.allow_editing_vaccination_billing);
			return false;
		},
		treatmentFieldLocked(row, field) {
			if (['Lab Order', 'Vaccination'].includes(row?.source_type)) {
				return field !== 'rate' || !this.sourceTreatmentRateEditable(row);
			}
			return this.treatmentRowLocked(row);
		},
		treatmentRemovalLocked(row) {
			if (['Lab Order', 'Vaccination'].includes(row?.source_type)) return true;
			return this.treatmentRowLocked(row);
		},
		treatmentRowLocked(row) {
			if (this.detail.scope_locked) return true;
			const billingLocked = !["Pending", "Skipped", "Cancelled", ""].includes(row?.billing_status || "Pending") || ["Paid", "Partly Paid", "Cancelled"].includes(row?.payment_status || "Not Billed");
			if (billingLocked) return true;
			if (this.isDefaultConsultationFee(row) && this.feePolicy.allow_editing_default_consultation_fee) return false;
			return Boolean(row?.source_document || row?.source_detail_name || ["Consultation", "Lab Order", "Vaccination"].includes(row?.source_type));
		},
		async saveConsultation() {
			if (this.busy) return null;
			this.busy = true; this.error = "";
			try {
				const payload = {
					...this.form,
					name: this.detail.name || undefined,
					modified: this.detail.modified || undefined,
					consultation_datetime: serverDatetime(this.form.consultation_datetime),
					follow_up_date: serverDatetime(this.form.follow_up_date),
					symptoms: this.form.symptoms.map(({ _key, ...row }) => row),
					diagnoses: this.form.diagnoses.map(({ _key, ...row }) => row),
					planned_treatments: this.form.planned_treatments.map(({ _key, ...row }) => row),
				};
				const detail = await call(API.save, { payload });
				this.applyDetail(detail); await this.applyTreatmentOrder();
				frappe.show_alert({ message: "Consultation saved.", indicator: "green" });
				window.history.replaceState({}, "", `/desk/vetedge-clinical-workspace?consultation=${encodeURIComponent(detail.name)}`);
				return detail;
			} catch (error) { this.error = message(error, "Consultation could not be saved."); return null; }
			finally { this.busy = false; }
		},
		async runAction(action) {
			if (this.dirty) { this.error = __("Save or discard consultation changes before running a workflow action."); return; }
			this.busy = true;
			try { this.applyDetail(await call(API.action, { name: this.detail.name, action: action.key, modified: this.detail.modified })); await this.applyTreatmentOrder(); frappe.show_alert({ message: `${action.label} completed.`, indicator: "green" }); }
			catch (error) { this.error = message(error, "Workflow action failed."); }
			finally { this.busy = false; }
		},
		openVitals() { if (!this.isNew && this.detail.capabilities.create_vitals) this.vitalsDialog = { open: true, values: {} }; },
		closeVitals() { if (!this.busy) this.vitalsDialog = { open: false, values: {} }; },
		setVital(field, value) { this.vitalsDialog.values = { ...this.vitalsDialog.values, [field]: value }; },
		async saveVitals() {
			this.busy = true;
			try { const result = await call(API.vitals, { name: this.detail.name, values: this.vitalsDialog.values, modified: this.detail.modified }); this.applyDetail(result.detail); this.vitalsDialog = { open: false, values: {} }; frappe.show_alert({ message: "Vitals recorded.", indicator: "green" }); }
			catch (error) { this.error = message(error, "Vitals could not be saved."); }
			finally { this.busy = false; }
		},
		async openHistory() {
			if (!this.detail.capabilities.view_history) return;
			this.historyDialog = { open: true, loading: true, data: {} };
			try { this.historyDialog.data = await call(API.history, { name: this.detail.name, limit: 20 }) || {}; }
			catch (error) { this.error = message(error, "Medical history unavailable."); this.historyDialog.open = false; }
			finally { this.historyDialog.loading = false; }
		},
		closeHistory() { this.historyDialog = { open: false, loading: false, data: {} }; },
		async openDispensary() {
			if (!this.detail.name) return;
			this.dispensaryDialog = { ...blankDispensary(), open: true, loading: true };
			try {
				const context = await call(API.dispensaryContext, { consultation: this.detail.name });
				this.dispensaryDialog.context = context || {};
				this.dispensaryDialog.items = (context?.items || []).map((row) => ({ ...row }));
			} catch (error) { this.error = message(error, __("Dispensary context could not be loaded.")); this.dispensaryDialog.open = false; }
			finally { this.dispensaryDialog.loading = false; }
		},
		closeDispensary() { if (!this.busy) this.dispensaryDialog = blankDispensary(); },
		updateDispensaryQty(index, value) { this.dispensaryDialog.items[index].dispensed_qty = value; },
		async confirmDispensary() {
			if (!this.detail.name || this.busy || !this.dispensaryDialog.context.can_confirm) return;
			this.busy = true;
			try {
				const result = await call(API.confirmDispensary, { consultation: this.detail.name, modified: this.detail.modified, dispensed_items: this.dispensaryDialog.items });
				this.applyDetail(result?.detail || await call(API.detail, { name: this.detail.name }));
				this.dispensaryDialog = blankDispensary();
				frappe.show_alert({ message: __("Dispensary issue confirmed."), indicator: "green" });
			} catch (error) { this.error = message(error, __("Dispensary issue could not be confirmed.")); }
			finally { this.busy = false; }
		},
		openBilling() {
			if (!window.vetedgeBillingModal?.open || this.isNew || !this.detail.capabilities.open_billing) return;
			const workspace = this;
			window.vetedgeBillingModal.open({ doc: { doctype: "Veterinary Consultation", name: this.detail.name }, is_new: () => false, is_dirty: () => workspace.dirty, save: () => workspace.saveConsultation(), reload_doc: () => workspace.loadDetail(workspace.detail.name) });
		},
		openRelated(doctype) { frappe.route_options = { consultation: this.detail.name, patient: this.form.patient }; frappe.set_route("List", doctype); },
		openDocument(doctype, name) { if (name) frappe.set_route("Form", doctype, name); },
		openRoute(route) {
			if (!route) return;
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge");
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
		async linkSearch(kind, search) { return (await call(API.links, { kind, search, branch: this.form.service_branch || this.filters.branch || undefined, limit: 20 })) || []; },
		async contextSearch(kind, search) { return (await call(API.contextLinks, { kind, search, limit: 50 })) || []; },
		formatMoney(value) { return typeof format_currency === "function" ? format_currency(value || 0) : Number(value || 0).toFixed(2); },
	},
};
</script>

<style scoped>
.clinical-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:var(--edge-space-3,.75rem);margin-bottom:var(--edge-space-5,1.25rem)}.clinical-filter-grid,.clinical-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--edge-space-4,1rem);width:100%}.clinical-wide{grid-column:1/-1}.clinical-detail,.clinical-panel,.clinical-history,.clinical-history section,.clinical-invoices,.clinical-dispensary{display:grid;gap:var(--edge-space-4,1rem)}.clinical-statusbar,.clinical-workflow{align-items:center;background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem);display:flex;gap:1rem;justify-content:space-between;padding:1rem}.clinical-context-badges,.clinical-row-actions{align-items:center;display:flex;flex-wrap:wrap;gap:.6rem}.clinical-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.6rem}.clinical-tab{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);color:var(--edge-color-ink-700,#334b61);display:grid;gap:.2rem;padding:.8rem;text-align:left}.clinical-tab.is-active{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-500,#1677c8);color:var(--edge-color-brand-700,#0c4f87)}.clinical-tab small,.clinical-subhead p,.clinical-workflow p,.clinical-dispensary p{color:var(--edge-color-ink-500,#617589);margin:0}.clinical-panel{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem);padding:1.15rem}.clinical-panel h3,.clinical-panel h4,.clinical-subhead h3,.clinical-subhead h4{margin:0}.clinical-subhead{align-items:center;border-top:1px solid var(--edge-color-border,#dfe6ec);display:flex;gap:1rem;justify-content:space-between;padding-top:1rem}.clinical-child-row,.clinical-treatment-row,.clinical-dispensary-row{align-items:end;background:var(--edge-color-surface-muted,#f6f8fa);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);display:grid;gap:.75rem;padding:.8rem}.clinical-child-row{grid-template-columns:1.2fr 1.5fr auto}.clinical-child-row--diagnosis{grid-template-columns:1.2fr .9fr 1.2fr auto}.clinical-treatment-row{grid-template-columns:1.2fr 1.4fr .55fr .65fr .9fr auto}.clinical-treatment-meta{display:grid;gap:.3rem}.clinical-vitals{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem}.clinical-vitals>div{border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);display:grid;gap:.3rem;padding:.8rem}.clinical-vitals span,.clinical-history article span,.clinical-history article p,.clinical-dispensary-row small{color:var(--edge-color-ink-500,#617589)}.clinical-empty{border:1px dashed var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);color:var(--edge-color-ink-500,#617589);padding:1rem}.clinical-history article{border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);display:grid;gap:.3rem;padding:.75rem}.clinical-history article p{margin:0}.clinical-dispensary-meta{display:grid;grid-template-columns:auto 1fr;gap:.45rem .75rem}.clinical-dispensary-meta span{color:var(--edge-color-ink-500,#617589)}.clinical-dispensary-row{grid-template-columns:1.2fr .7fr .7fr .8fr}.clinical-dispensary-row>div{display:grid;gap:.2rem}@media(max-width:70rem){.clinical-summary{grid-template-columns:repeat(3,1fr)}.clinical-treatment-row,.clinical-dispensary-row{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:48rem){.clinical-summary,.clinical-filter-grid,.clinical-grid,.clinical-tabs,.clinical-vitals,.clinical-child-row,.clinical-child-row--diagnosis,.clinical-treatment-row,.clinical-dispensary-row{grid-template-columns:1fr}.clinical-wide{grid-column:auto}.clinical-statusbar,.clinical-workflow,.clinical-subhead{align-items:stretch;flex-direction:column}}
</style>