<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-clinical-workspace"
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
					<div class="vetedge-clinical-filters">
						<EdgeLinkField
							:model-value="filters.branch"
							label="Branch"
							placeholder="All permitted branches"
							:searcher="(query) => linkSearch('branch', query)"
							@update:model-value="(value) => setFilter('branch', value)"
						/>
						<EdgeLinkField
							:model-value="filters.practitioner"
							label="Practitioner"
							placeholder="All doctors"
							:searcher="(query) => linkSearch('practitioner', query)"
							@update:model-value="(value) => setFilter('practitioner', value)"
						/>
						<label class="vetedge-clinical-field">
							<span>Status</span>
							<select v-model="filters.status" class="form-control">
								<option value="">All statuses</option>
								<option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
							</select>
						</label>
						<label class="vetedge-clinical-field vetedge-clinical-field--search">
							<span>Search</span>
							<input
								v-model.trim="filters.search"
								type="search"
								class="form-control"
								placeholder="Consultation, patient, owner or complaint"
								@keyup.enter="applyFilters"
							/>
						</label>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<template v-if="!detail.open">
				<section class="vetedge-clinical-summary" aria-label="Consultation summary">
					<EdgeStatCard label="Draft" :value="summary.draft || 0" icon="file-pen-line" />
					<EdgeStatCard label="In progress" :value="summary.in_progress || 0" icon="stethoscope" />
					<EdgeStatCard label="Awaiting payment" :value="summary.awaiting_payment || 0" icon="credit-card" />
					<EdgeStatCard label="Ready for treatment" :value="summary.ready_for_treatment || 0" icon="clipboard-check" />
					<EdgeStatCard label="Completed" :value="summary.completed || 0" icon="circle-check" />
				</section>

				<EdgeLoadingState v-if="loading" message="Loading consultations..." :skeleton="true" />
				<EdgeErrorState
					v-else-if="error"
					title="Consultations could not load"
					:message="error"
					action-label="Try again"
					@retry="refreshList"
				/>
				<EdgeDataTable
					v-else
					:columns="listColumns"
					:rows="consultations.rows || []"
					empty-title="No consultations"
					empty-description="No consultations match the current filters."
					@row-click="openConsultation"
				>
					<template #footer>
						<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ consultations.total || 0 }}</span>
						<div class="vetedge-clinical-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext" @click="nextPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>

			<template v-else>
				<EdgeLoadingState v-if="detail.loading" message="Loading consultation..." :skeleton="true" />
				<EdgeErrorState
					v-else-if="detail.error"
					title="Consultation could not load"
					:message="detail.error"
					action-label="Back to list"
					@retry="backToList"
				/>
				<div v-else class="vetedge-clinical-detail">
					<section class="vetedge-clinical-statusbar">
						<div>
							<EdgeStatusBadge :label="detail.status || 'Draft'" :status="detail.status || 'Draft'" />
							<span>Payment: <strong>{{ form.payment_status || 'Not Billed' }}</strong></span>
							<span>Dispensary: <strong>{{ form.dispensary_status || 'Not Required' }}</strong></span>
						</div>
						<div class="vetedge-clinical-actions">
							<button type="button" class="edge-button" :disabled="busy || isNew || !detail.capabilities.view_history" @click="openHistory">Medical History</button>
							<button type="button" class="edge-button" :disabled="busy || isNew || !detail.capabilities.create_vitals" @click="openVitals">New Vitals</button>
							<button type="button" class="edge-button" :disabled="busy || isNew || !detail.capabilities.open_billing" @click="openBilling">Billing & Payment</button>
							<button type="button" class="edge-button edge-button--primary" :disabled="busy || !detail.can_write" @click="saveConsultation">{{ busy ? 'Saving…' : 'Save Consultation' }}</button>
						</div>
					</section>

					<nav class="vetedge-clinical-tabs" aria-label="Consultation sections">
						<button
							v-for="tab in tabs"
							:key="tab.value"
							type="button"
							:class="{ 'is-active': activeTab === tab.value }"
							@click="activeTab = tab.value"
						>
							<span>{{ tab.label }}</span>
							<small>{{ tab.description }}</small>
						</button>
					</nav>

					<section v-if="activeTab === 'visit'" class="vetedge-clinical-panel">
						<h3>Patient and Visit</h3>
						<div class="vetedge-clinical-grid">
							<EdgeLinkField :model-value="form.patient" label="Patient" placeholder="Select patient" :disabled="identityLocked" :searcher="(query) => linkSearch('patient', query)" @update:model-value="(value) => updateField('patient', value)" />
							<EdgeLinkField :model-value="form.service_branch" label="Service Branch" placeholder="Select branch" :disabled="identityLocked" :searcher="(query) => linkSearch('branch', query)" @update:model-value="(value) => updateField('service_branch', value)" />
							<EdgeLinkField :model-value="form.consulting_practitioner" label="Consulting Practitioner" placeholder="Select doctor" :searcher="(query) => linkSearch('practitioner', query)" @update:model-value="(value) => updateField('consulting_practitioner', value)" />
							<EdgeLinkField :model-value="form.consultation_type" label="Consultation Type" placeholder="Select consultation type" :searcher="(query) => linkSearch('consultation_type', query)" @update:model-value="(value) => updateField('consultation_type', value)" />
							<label class="vetedge-clinical-field">
								<span>Consultation Date/Time</span>
								<input v-model="form.consultation_datetime" type="datetime-local" class="form-control" @input="markDirty" />
							</label>
							<label class="vetedge-clinical-field vetedge-clinical-field--wide">
								<span>Presenting Complaint</span>
								<textarea v-model="form.presenting_complaint" class="form-control" rows="4" @input="markDirty"></textarea>
							</label>
						</div>
						<div v-if="!isNew" class="vetedge-clinical-related">
							<button type="button" class="edge-button edge-button--compact" @click="openRelated('Veterinary Lab Order')">Laboratory Orders</button>
							<button type="button" class="edge-button edge-button--compact" @click="openRelated('Veterinary Vaccination Record')">Vaccinations</button>
							<button type="button" class="edge-button edge-button--compact" @click="openRelated('Veterinary Hospitalisation')">Hospitalisation</button>
							<button v-if="form.linked_appointment" type="button" class="edge-button edge-button--compact" @click="openDocument('Veterinary Appointment', form.linked_appointment)">Service Appointment</button>
							<button v-if="form.follow_up_appointment" type="button" class="edge-button edge-button--compact" @click="openDocument('Veterinary Appointment', form.follow_up_appointment)">Follow-up Appointment</button>
						</div>
					</section>

					<section v-if="activeTab === 'clinical'" class="vetedge-clinical-panel">
						<h3>Clinical Findings</h3>
						<div class="vetedge-clinical-stack">
							<label class="vetedge-clinical-field"><span>Examination Notes</span><textarea v-model="form.examination_notes" class="form-control" rows="5" @input="markDirty"></textarea></label>
							<label class="vetedge-clinical-field"><span>Assessment Notes</span><textarea v-model="form.assessment_notes" class="form-control" rows="5" @input="markDirty"></textarea></label>
						</div>

						<header class="vetedge-clinical-subhead">
							<div><h4>Symptoms</h4><p>Capture only active and clinically relevant symptoms.</p></div>
							<button type="button" class="edge-button edge-button--compact" :disabled="!detail.can_write" @click="addSymptom">Add Symptom</button>
						</header>
						<div v-for="(row, index) in form.symptoms" :key="row._key || row.name || index" class="vetedge-clinical-childrow">
							<EdgeLinkField :model-value="row.symptom" label="Symptom" placeholder="Select symptom" :searcher="(query) => linkSearch('symptom', query)" @update:model-value="(value) => updateChild('symptoms', index, 'symptom', value)" />
							<label class="vetedge-clinical-field"><span>Notes</span><input v-model="row.notes" class="form-control" @input="markDirty" /></label>
							<button type="button" class="edge-button edge-button--danger edge-button--compact" @click="removeChild('symptoms', index)">Remove</button>
						</div>

						<header class="vetedge-clinical-subhead">
							<div><h4>Diagnoses</h4><p>Diagnosis and treatment capture remains restricted by existing Veterinary Doctor permissions.</p></div>
							<button type="button" class="edge-button edge-button--compact" :disabled="!detail.can_write" @click="addDiagnosis">Add Diagnosis</button>
						</header>
						<div v-for="(row, index) in form.diagnoses" :key="row._key || row.name || index" class="vetedge-clinical-childrow vetedge-clinical-childrow--diagnosis">
							<EdgeLinkField :model-value="row.diagnosis" label="Diagnosis" placeholder="Select diagnosis" :searcher="(query) => linkSearch('diagnosis', query)" @update:model-value="(value) => updateChild('diagnoses', index, 'diagnosis', value)" />
							<label class="vetedge-clinical-field"><span>Diagnosis Type</span><select v-model="row.diagnosis_type" class="form-control" @change="markDirty"><option value=""></option><option v-for="type in diagnosisTypes" :key="type" :value="type">{{ type }}</option></select></label>
							<label class="vetedge-clinical-field"><span>Notes</span><input v-model="row.notes" class="form-control" @input="markDirty" /></label>
							<button type="button" class="edge-button edge-button--danger edge-button--compact" @click="removeChild('diagnoses', index)">Remove</button>
						</div>
					</section>

					<section v-if="activeTab === 'treatment'" class="vetedge-clinical-panel">
						<header class="vetedge-clinical-subhead">
							<div>
								<h3>Treatment Plan</h3>
								<p v-if="detail.scope_locked" class="text-warning">Treatment scope is locked because this consultation is {{ detail.status }}. Existing billing-safe rows remain visible.</p>
								<p v-else>Add treatment rows before the consultation reaches Ready for Treatment.</p>
							</div>
							<button type="button" class="edge-button edge-button--compact" :disabled="detail.scope_locked || !detail.can_write" @click="addTreatment">Add Treatment</button>
						</header>
						<label class="vetedge-clinical-field"><span>Treatment Plan Summary</span><textarea v-model="form.treatment_plan_summary" class="form-control" rows="4" @input="markDirty"></textarea></label>
						<div v-for="(row, index) in form.planned_treatments" :key="row._key || row.name || index" class="vetedge-clinical-treatmentrow">
							<EdgeLinkField :model-value="row.item" label="Treatment Item" placeholder="Select treatment item" :disabled="treatmentRowLocked(row)" :searcher="(query) => linkSearch('treatment_item', query)" @update:model-value="(value) => updateTreatmentItem(index, value)" />
							<label class="vetedge-clinical-field vetedge-clinical-field--wide"><span>Description</span><input v-model="row.description" class="form-control" :disabled="treatmentRowLocked(row)" @input="markDirty" /></label>
							<label class="vetedge-clinical-field"><span>Qty</span><input v-model.number="row.qty" type="number" min="0.001" step="0.001" class="form-control" :disabled="treatmentRowLocked(row)" @input="markDirty" /></label>
							<label class="vetedge-clinical-field"><span>Rate</span><input v-model.number="row.rate" type="number" min="0" step="0.01" class="form-control" :disabled="treatmentRowLocked(row)" @input="markDirty" /></label>
							<div class="vetedge-clinical-treatmentmeta"><EdgeStatusBadge :label="row.billing_status || 'Pending'" :status="row.billing_status || 'Pending'" /><span>{{ row.payment_status || 'Not Billed' }}</span><strong>{{ formatMoney((Number(row.qty) || 0) * (Number(row.rate) || 0)) }}</strong></div>
							<button type="button" class="edge-button edge-button--danger edge-button--compact" :disabled="treatmentRowLocked(row)" @click="removeChild('planned_treatments', index)">Remove</button>
						</div>
						<label class="vetedge-clinical-field"><span>Follow-up Date</span><input v-model="form.follow_up_date" type="date" class="form-control" @input="markDirty" /></label>
					</section>

					<section v-if="activeTab === 'vitals'" class="vetedge-clinical-panel">
						<h3>Latest Vitals and Billing Context</h3>
						<div v-if="detail.latest_vitals" class="vetedge-clinical-vitals">
							<div v-for="entry in vitalEntries" :key="entry.label"><span>{{ entry.label }}</span><strong>{{ entry.value || '—' }}</strong></div>
						</div>
						<div v-else class="vetedge-clinical-empty">No vitals have been recorded for this consultation.</div>
						<div class="vetedge-clinical-invoices">
							<h4>Consultation Invoices</h4>
							<div v-if="!(form.consultation_invoices || []).length" class="vetedge-clinical-empty">No consultation invoice references yet.</div>
							<button v-for="invoice in form.consultation_invoices || []" :key="invoice.invoice || invoice.name" type="button" class="edge-button edge-button--compact" @click="openDocument('Sales Invoice', invoice.invoice || invoice.name)">{{ invoice.invoice || invoice.name }} · {{ invoice.payment_status || invoice.status || 'Open' }}</button>
						</div>
					</section>

					<section v-if="!isNew && (detail.actions || []).length" class="vetedge-clinical-workflow">
						<div><h3>Workflow Actions</h3><p>Transitions use existing consultation payment, dispensary, cancellation and completion gates.</p></div>
						<div>
							<button v-for="action in detail.actions" :key="action.key" type="button" :class="['edge-button', action.danger ? 'edge-button--danger' : action.primary ? 'edge-button--primary' : '']" :disabled="busy" @click="runAction(action)">{{ action.label }}</button>
						</div>
					</section>
				</div>
			</template>
		</EdgePageLayout>

		<EdgeModal :open="vitalsDialog.open" title="Record Veterinary Vitals" subtitle="Vitals remain separate clinical records linked to this consultation." :busy="busy" @close="closeVitals">
			<div class="vetedge-clinical-grid">
				<label v-for="field in vitalFields" :key="field.name" class="vetedge-clinical-field"><span>{{ field.label }}</span><input v-model="vitalsDialog.values[field.name]" :type="field.type || 'text'" :min="field.min" :step="field.step" class="form-control" /></label>
				<label class="vetedge-clinical-field vetedge-clinical-field--wide"><span>Notes</span><textarea v-model="vitalsDialog.values.notes" class="form-control" rows="4"></textarea></label>
			</div>
			<template #footer>
				<button type="button" class="edge-button" :disabled="busy" @click="closeVitals">Cancel</button>
				<button type="button" class="edge-button edge-button--primary" :disabled="busy" @click="saveVitals">Save Vitals</button>
			</template>
		</EdgeModal>

		<EdgeModal :open="historyDialog.open" title="Patient Medical History" :subtitle="historySubtitle" :busy="historyDialog.loading" @close="closeHistory">
			<EdgeLoadingState v-if="historyDialog.loading" message="Loading medical history..." :skeleton="true" />
			<div v-else class="vetedge-clinical-history">
				<section v-for="section in historySections" :key="section.label">
					<h4>{{ section.label }}</h4>
					<div v-if="!section.rows.length" class="vetedge-clinical-empty">No records.</div>
					<article v-for="row in section.rows" :key="row.name || row.timestamp">
						<strong>{{ row.title || row.name || row.vaccine || row.tests_summary || 'Clinical record' }}</strong>
						<span>{{ row.status || row.payment_status || '' }}</span>
						<p>{{ row.presenting_complaint || row.assessment_notes || row.results_summary || row.notes || '' }}</p>
					</article>
				</section>
			</div>
			<template #footer><button type="button" class="edge-button" @click="closeHistory">Close</button></template>
		</EdgeModal>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	summary: "vetedge.services.clinical_workspace.get_clinical_summary",
	list: "vetedge.services.clinical_workspace.get_consultations",
	detail: "vetedge.services.clinical_workspace.get_consultation_detail",
	save: "vetedge.services.clinical_workspace.save_consultation",
	action: "vetedge.services.clinical_workspace.perform_consultation_action",
	vitals: "vetedge.services.clinical_workspace.create_consultation_vitals",
	history: "vetedge.services.clinical_workspace.get_consultation_history",
	links: "vetedge.services.clinical_workspace.get_clinical_link_options",
	defaults: "vetedge.services.clinical_workspace.get_treatment_defaults",
});
const STATUSES = ["Draft", "In Progress", "Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled"];
const blankCapabilities = () => ({ create_vitals: false, view_history: false, open_billing: false });
const blankDetail = (overrides = {}) => ({ open: false, loading: false, error: "", name: "", modified: "", status: "Draft", can_write: true, scope_locked: false, latest_vitals: null, actions: [], capabilities: blankCapabilities(), ...overrides });
const blankForm = () => ({ patient: "", consultation_datetime: "", consultation_type: "General Consultation", service_branch: "", consulting_practitioner: "", linked_appointment: "", presenting_complaint: "", examination_notes: "", assessment_notes: "", treatment_plan_summary: "", follow_up_date: "", symptoms: [], diagnoses: [], planned_treatments: [], consultation_invoices: [], payment_status: "Not Billed", dispensary_status: "Not Required" });
function call(method, args = {}) { return frappe.call({ method, args }).then((response) => response.message); }
function message(error, fallback) { return error?.message || error?._server_messages || error?.exc_type || fallback; }
function localDatetime(value) { if (!value) return ""; return String(value).replace(" ", "T").slice(0, 16); }
function serverDatetime(value) { return value ? String(value).replace("T", " ") : value; }
function rowKey(row) { return row?.name || window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`; }

export default {
	name: "VetEdgeClinicalWorkspace",
	data() {
		return {
			identity: window.frappe?.boot?.vetedge_ui_identity || {},
			statuses: STATUSES,
			diagnosisTypes: ["Primary", "Differential", "Rule Out", "Resolved"],
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
			vitalsDialog: { open: false, values: {} },
			historyDialog: { open: false, loading: false, data: {} },
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
		userName() { return window.frappe?.session?.user_fullname || window.frappe?.session?.user || ""; },
		branchName() { return this.form.service_branch || this.filters.branch || ""; },
		isNew() { return !this.detail.name; },
		identityLocked() { return !this.isNew && this.detail.status !== "Draft"; },
		detailTitle() { return this.form.consultation_title || this.detail.name || "New Veterinary Consultation"; },
		detailSubtitle() { return [this.form.patient, this.form.consulting_practitioner_name, this.form.service_branch].filter(Boolean).join(" · ") || "Clinical consultation capture"; },
		firstVisible() { return this.consultations.total ? this.consultations.start + 1 : 0; },
		lastVisible() { return Math.min(this.consultations.start + (this.consultations.rows || []).length, this.consultations.total || 0); },
		hasPrevious() { return this.consultations.start > 0; },
		hasNext() { return this.consultations.start + this.consultations.page_length < this.consultations.total; },
		vitalEntries() {
			const v = this.detail.latest_vitals || {};
			return [
				["Recorded On", frappe.datetime?.str_to_user?.(v.recorded_on) || v.recorded_on],
				["Temperature", v.temperature],
				["Weight", v.weight],
				["Heart Rate", v.heart_rate],
				["Respiratory Rate", v.respiratory_rate],
				["Body Condition", v.body_condition_score],
				["Hydration", v.hydration_status],
				["Pain Score", v.pain_score],
				["Appetite", v.appetite_status],
			].map(([label, value]) => ({ label, value }));
		},
		historySubtitle() { return this.historyDialog.data?.summary?.patient_name || this.form.patient || "Patient"; },
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
	mounted() {
		const params = new URLSearchParams(window.location.search || "");
		if (params.get("consultation")) {
			this.loadDetail(params.get("consultation"));
			return;
		}
		if (params.has("new")) {
			this.startNewConsultation();
			return;
		}
		this.refreshList();
	},
	methods: {
		async refreshList() {
			this.loading = true;
			this.error = "";
			try {
				const [summary, consultations] = await Promise.all([
					call(API.summary, { branch: this.filters.branch || undefined }),
					call(API.list, { ...this.filters, start: this.consultations.start || 0, page_length: this.consultations.page_length || 25 }),
				]);
				this.summary = summary || {};
				this.consultations = consultations || { rows: [], total: 0, start: 0, page_length: 25 };
			} catch (error) {
				this.error = message(error, "Unable to load consultations.");
			} finally {
				this.loading = false;
			}
		},
		applyFilters() { this.consultations.start = 0; return this.refreshList(); },
		resetFilters() { this.filters = { branch: "", practitioner: "", status: "", search: "" }; this.consultations.start = 0; return this.refreshList(); },
		setFilter(field, value) { this.filters[field] = value || ""; },
		previousPage() { this.consultations.start = Math.max(0, this.consultations.start - this.consultations.page_length); this.refreshList(); },
		nextPage() { this.consultations.start += this.consultations.page_length; this.refreshList(); },
		openConsultation(row) { return this.loadDetail(row.name); },
		async loadDetail(name) {
			this.detail = blankDetail({ open: true, loading: true, name, can_write: false });
			this.activeTab = "visit";
			try {
				const payload = await call(API.detail, { name });
				this.applyDetail(payload);
				window.history.replaceState({}, "", `/app/vetedge-clinical-workspace?consultation=${encodeURIComponent(name)}`);
			} catch (error) {
				this.detail.loading = false;
				this.detail.error = message(error, "Unable to load consultation.");
			}
		},
		applyDetail(payload) {
			const values = payload?.values || {};
			this.detail = blankDetail({
				open: true,
				name: payload?.name || "",
				modified: payload?.modified || "",
				status: payload?.status || "Draft",
				can_write: payload?.can_write !== false,
				scope_locked: Boolean(payload?.scope_locked),
				latest_vitals: payload?.latest_vitals || null,
				actions: payload?.actions || [],
				capabilities: { ...blankCapabilities(), ...(payload?.capabilities || {}) },
			});
			this.form = {
				...blankForm(),
				...values,
				consultation_datetime: localDatetime(values.consultation_datetime),
				symptoms: (values.symptoms || []).map((row) => ({ ...row, _key: rowKey(row) })),
				diagnoses: (values.diagnoses || []).map((row) => ({ ...row, _key: rowKey(row) })),
				planned_treatments: (values.planned_treatments || []).map((row) => ({ ...row, _key: rowKey(row) })),
			};
			this.dirty = false;
		},
		startNewConsultation() {
			this.detail = blankDetail({ open: true, can_write: true });
			this.form = blankForm();
			this.activeTab = "visit";
			this.dirty = false;
			window.history.replaceState({}, "", "/app/vetedge-clinical-workspace?new=1");
		},
		backToList() {
			this.detail = blankDetail();
			this.form = blankForm();
			this.dirty = false;
			window.history.replaceState({}, "", "/app/vetedge-clinical-workspace");
			this.refreshList();
		},
		markDirty() { this.dirty = true; },
		updateField(field, value) { this.form[field] = value || ""; this.markDirty(); },
		updateChild(table, index, field, value) { this.form[table][index][field] = value || ""; this.markDirty(); },
		addSymptom() { this.form.symptoms.push({ _key: rowKey(), symptom: "", notes: "" }); this.markDirty(); },
		addDiagnosis() { this.form.diagnoses.push({ _key: rowKey(), diagnosis: "", diagnosis_type: "", notes: "" }); this.markDirty(); },
		addTreatment() { this.form.planned_treatments.push({ _key: rowKey(), item: "", description: "", qty: 1, rate: 0, billing_status: "Pending", payment_status: "Not Billed" }); this.markDirty(); },
		removeChild(table, index) { this.form[table].splice(index, 1); this.markDirty(); },
		async updateTreatmentItem(index, item) {
			const row = this.form.planned_treatments[index];
			row.item = item || "";
			this.markDirty();
			if (!item) return;
			try {
				const defaults = await call(API.defaults, { item, company: this.form.company, customer: this.form.primary_owner, branch: this.form.service_branch });
				Object.assign(row, { uom: defaults?.uom || row.uom, rate: defaults?.rate ?? row.rate, service_type: defaults?.service_type || row.service_type, treatment_type: defaults?.treatment_type || row.treatment_type });
			} catch (error) {
				frappe.show_alert({ message: message(error, "Treatment defaults could not load."), indicator: "orange" });
			}
		},
		treatmentRowLocked(row) { return this.detail.scope_locked || !["Pending", "Skipped", "Cancelled", ""].includes(row.billing_status || "Pending"); },
		async saveConsultation() {
			if (this.busy) return;
			this.busy = true;
			try {
				const payload = {
					...this.form,
					name: this.detail.name || undefined,
					modified: this.detail.modified || undefined,
					consultation_datetime: serverDatetime(this.form.consultation_datetime),
					symptoms: this.form.symptoms.map(({ _key, ...row }) => row),
					diagnoses: this.form.diagnoses.map(({ _key, ...row }) => row),
					planned_treatments: this.form.planned_treatments.map(({ _key, ...row }) => row),
				};
				const detail = await call(API.save, { payload });
				this.applyDetail(detail);
				frappe.show_alert({ message: "Consultation saved.", indicator: "green" });
				window.history.replaceState({}, "", `/app/vetedge-clinical-workspace?consultation=${encodeURIComponent(detail.name)}`);
				return detail;
			} catch (error) {
				frappe.msgprint({ title: "Consultation could not be saved", message: message(error, "Save failed."), indicator: "red" });
				return null;
			} finally {
				this.busy = false;
			}
		},
		async runAction(action) {
			if (this.dirty) { frappe.msgprint("Save or discard consultation changes before running a workflow action."); return; }
			this.busy = true;
			try {
				const detail = await call(API.action, { name: this.detail.name, action: action.key, modified: this.detail.modified });
				this.applyDetail(detail);
				frappe.show_alert({ message: `${action.label} completed.`, indicator: "green" });
			} catch (error) {
				frappe.msgprint({ title: "Workflow action failed", message: message(error, "Action failed."), indicator: "red" });
			} finally {
				this.busy = false;
			}
		},
		openVitals() { if (!this.isNew && this.detail.capabilities.create_vitals) this.vitalsDialog = { open: true, values: {} }; },
		closeVitals() { if (!this.busy) this.vitalsDialog = { open: false, values: {} }; },
		async saveVitals() {
			this.busy = true;
			try {
				const result = await call(API.vitals, { name: this.detail.name, values: this.vitalsDialog.values, modified: this.detail.modified });
				this.applyDetail(result.detail);
				this.closeVitals();
				frappe.show_alert({ message: "Vitals recorded.", indicator: "green" });
			} catch (error) {
				frappe.msgprint({ title: "Vitals could not be saved", message: message(error, "Vitals failed."), indicator: "red" });
			} finally {
				this.busy = false;
			}
		},
		async openHistory() {
			if (!this.detail.capabilities.view_history) return;
			this.historyDialog = { open: true, loading: true, data: {} };
			try {
				this.historyDialog.data = await call(API.history, { name: this.detail.name, limit: 20 }) || {};
			} catch (error) {
				frappe.msgprint({ title: "Medical history unavailable", message: message(error, "History failed."), indicator: "red" });
				this.historyDialog.open = false;
			} finally {
				this.historyDialog.loading = false;
			}
		},
		closeHistory() { this.historyDialog = { open: false, loading: false, data: {} }; },
		openBilling() {
			if (!window.vetedgeBillingModal?.open || this.isNew || !this.detail.capabilities.open_billing) return;
			const workspace = this;
			window.vetedgeBillingModal.open({
				doc: { doctype: "Veterinary Consultation", name: this.detail.name },
				is_new: () => false,
				is_dirty: () => workspace.dirty,
				save: () => workspace.saveConsultation(),
				reload_doc: () => workspace.loadDetail(workspace.detail.name),
			});
		},
		openRelated(doctype) { frappe.route_options = { consultation: this.detail.name, patient: this.form.patient }; frappe.set_route("List", doctype); },
		openDocument(doctype, name) { if (name) frappe.set_route("Form", doctype, name); },
		openRoute(route) { if (route) window.location.assign(route); },
		async linkSearch(kind, search) { return (await call(API.links, { kind, search, branch: this.form.service_branch || this.filters.branch || undefined, limit: 20 })) || []; },
		formatMoney(value) { return typeof format_currency === "function" ? format_currency(value || 0) : Number(value || 0).toFixed(2); },
	},
};
</script>

<style scoped>
.vetedge-clinical-summary { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }
.vetedge-clinical-filters, .vetedge-clinical-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; width: 100%; }
.vetedge-clinical-field { display: grid; gap: 6px; min-width: 0; }
.vetedge-clinical-field > span { font-size: 12px; font-weight: 600; color: var(--text-muted); }
.vetedge-clinical-field--wide, .vetedge-clinical-field--search { grid-column: 1 / -1; }
.vetedge-clinical-pagination, .vetedge-clinical-actions, .vetedge-clinical-related, .vetedge-clinical-workflow > div:last-child { display: flex; flex-wrap: wrap; gap: 8px; }
.vetedge-clinical-statusbar, .vetedge-clinical-workflow { display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 14px; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-bg); margin-bottom: 14px; }
.vetedge-clinical-statusbar > div:first-child { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; }
.vetedge-clinical-tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px; }
.vetedge-clinical-tabs button { display: grid; gap: 3px; text-align: left; padding: 12px; border: 1px solid var(--border-color); border-radius: 10px; background: var(--card-bg); }
.vetedge-clinical-tabs button.is-active { border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary); }
.vetedge-clinical-tabs small, .vetedge-clinical-subhead p, .vetedge-clinical-workflow p { color: var(--text-muted); }
.vetedge-clinical-panel { display: grid; gap: 16px; padding: 18px; border: 1px solid var(--border-color); border-radius: 12px; background: var(--card-bg); }
.vetedge-clinical-stack { display: grid; gap: 14px; }
.vetedge-clinical-subhead { display: flex; justify-content: space-between; align-items: center; gap: 14px; border-top: 1px solid var(--border-color); padding-top: 16px; }
.vetedge-clinical-subhead h3, .vetedge-clinical-subhead h4, .vetedge-clinical-panel h3, .vetedge-clinical-panel h4 { margin: 0; }
.vetedge-clinical-childrow, .vetedge-clinical-treatmentrow { display: grid; grid-template-columns: 1.2fr 1.5fr auto; gap: 12px; align-items: end; padding: 12px; border: 1px solid var(--border-color); border-radius: 10px; }
.vetedge-clinical-childrow--diagnosis { grid-template-columns: 1.2fr .8fr 1.2fr auto; }
.vetedge-clinical-treatmentrow { grid-template-columns: 1.2fr 1.5fr .5fr .6fr 1fr auto; }
.vetedge-clinical-treatmentmeta { display: grid; gap: 4px; }
.vetedge-clinical-vitals { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.vetedge-clinical-vitals > div { display: grid; gap: 5px; padding: 12px; border: 1px solid var(--border-color); border-radius: 10px; }
.vetedge-clinical-vitals span { color: var(--text-muted); font-size: 12px; }
.vetedge-clinical-empty { padding: 16px; border: 1px dashed var(--border-color); border-radius: 10px; color: var(--text-muted); }
.vetedge-clinical-invoices, .vetedge-clinical-history, .vetedge-clinical-history section { display: grid; gap: 10px; }
.vetedge-clinical-history article { display: grid; gap: 4px; padding: 10px; border: 1px solid var(--border-color); border-radius: 8px; }
.vetedge-clinical-history article span, .vetedge-clinical-history article p { color: var(--text-muted); margin: 0; }
@media (max-width: 1100px) { .vetedge-clinical-summary { grid-template-columns: repeat(3, 1fr); } .vetedge-clinical-treatmentrow { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 767px) { .vetedge-clinical-summary, .vetedge-clinical-filters, .vetedge-clinical-grid, .vetedge-clinical-tabs, .vetedge-clinical-vitals, .vetedge-clinical-childrow, .vetedge-clinical-childrow--diagnosis, .vetedge-clinical-treatmentrow { grid-template-columns: 1fr; } .vetedge-clinical-statusbar, .vetedge-clinical-workflow, .vetedge-clinical-subhead { align-items: stretch; flex-direction: column; } }
</style>
