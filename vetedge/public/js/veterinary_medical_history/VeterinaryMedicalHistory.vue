<template>
	<EdgeAppShell
		product="veterinary"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/veterinary-medical-history"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Clinical Intelligence"
					title="Medical History"
					subtitle="Review a patient's longitudinal consultations, vitals trends, diagnoses, symptoms, treatments, vaccinations and laboratory history."
					action-label="Refresh"
					@action="load"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar title="Medical history filters">
					<div class="history-filter-grid">
						<EdgeLinkField
							:model-value="filters.patient"
							:selected-label="patientLabel"
							label="Veterinary Patient"
							placeholder="Select patient"
							:searcher="searchPatients"
							@update:model-value="selectPatient"
						/>
						<EdgeInput v-model="filters.from_date" type="date" label="From Date" />
						<EdgeInput v-model="filters.to_date" type="date" label="To Date" />
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading || !filters.patient" @click="load">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetDates">Last 90 Days</button>
					</template>
				</EdgeFilterBar>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading medical history..." :skeleton="true" />
			<EdgeErrorState v-else-if="error" title="Medical history could not load" :message="error" action-label="Try again" @retry="load" />
			<EdgeEmptyState
				v-else-if="!filters.patient"
				title="Select a Veterinary Patient"
				description="Choose a patient and date range to review longitudinal clinical history and vital trends."
			/>

			<template v-else>
				<section class="history-summary" aria-label="Patient medical history summary">
					<div class="history-patient-card">
						<span>Patient</span>
						<strong>{{ summary.patient_name || summary.patient || filters.patient }}</strong>
						<small>{{ [summary.species, summary.breed].filter(Boolean).join(' · ') || 'Veterinary Patient' }}</small>
					</div>
					<div class="history-summary-card"><span>Owner</span><strong>{{ summary.primary_owner || '—' }}</strong></div>
					<div class="history-summary-card"><span>Default Branch</span><strong>{{ summary.default_branch || '—' }}</strong></div>
					<div class="history-summary-card"><span>Latest Consultation</span><strong>{{ formatDateTime(summary.latest_consultation_date) || '—' }}</strong></div>
					<div class="history-summary-card"><span>Latest Weight</span><strong>{{ displayValue(summary.latest_weight) }}</strong></div>
					<div class="history-summary-card"><span>Latest Temperature</span><strong>{{ displayValue(summary.latest_temperature) }}</strong></div>
				</section>

				<section class="history-card history-trends">
					<header class="history-card-header">
						<div>
							<p class="edge-eyebrow">Vitals trends</p>
							<h2>Clinical Trend Charts</h2>
							<p>Switch between chart tabs to follow the patient's vital-sign changes over the selected period.</p>
						</div>
						<span class="history-period">{{ filters.from_date }} → {{ filters.to_date }}</span>
					</header>

					<nav class="history-tabs" aria-label="Vitals trend charts">
						<button
							v-for="trend in trendTabs"
							:key="trend.value"
							type="button"
							:class="['history-tab', { 'is-active': activeTrend === trend.value }]"
							@click="activeTrend = trend.value"
						>
							{{ trend.label }}
						</button>
					</nav>

					<div class="history-chart-shell">
						<div v-if="!activeTrendRows.length" class="history-chart-empty">No chart data in this range.</div>
						<div v-else ref="trendChart" class="history-chart" :data-trend="activeTrend"></div>
					</div>
				</section>

				<section class="history-card history-records">
					<header class="history-card-header">
						<div>
							<p class="edge-eyebrow">Longitudinal record</p>
							<h2>Medical History Sections</h2>
							<p>Clinical events remain grouped by source so the original record and workflow context are clear.</p>
						</div>
					</header>

					<nav class="history-tabs history-tabs--records" aria-label="Medical history sections">
						<button
							v-for="section in historyTabs"
							:key="section.value"
							type="button"
							:class="['history-tab', { 'is-active': activeHistory === section.value }]"
							@click="activeHistory = section.value"
						>
							<span>{{ section.label }}</span>
							<small>{{ rowsFor(section.value).length }}</small>
						</button>
					</nav>

					<EdgeDataTable
						:columns="activeHistoryColumns"
						:rows="activeHistoryRows"
						empty-title="No records in this range"
						empty-description="There are no records for this medical-history section in the selected date range."
						@row-click="openHistoryRow"
					/>
				</section>
			</template>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	history: "vetedge.services.medical_history.get_patient_medical_history_view",
});

const TREND_TABS = Object.freeze([
	{ value: "temperature", label: "Temperature" },
	{ value: "weight", label: "Weight" },
	{ value: "heart_rate", label: "Heart Rate" },
	{ value: "respiratory_rate", label: "Respiratory Rate" },
]);

const HISTORY_TABS = Object.freeze([
	{ value: "consultations", label: "Consultations" },
	{ value: "vitals", label: "Vitals" },
	{ value: "diagnoses", label: "Diagnoses" },
	{ value: "symptoms", label: "Symptoms" },
	{ value: "treatments", label: "Treatments" },
	{ value: "vaccinations", label: "Vaccinations" },
	{ value: "labs", label: "Laboratory" },
]);

const COLUMNS = Object.freeze({
	consultations: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "title", label: "Consultation" },
		{ key: "practitioner", label: "Practitioner" },
		{ key: "service_branch", label: "Branch" },
		{ key: "status", label: "Status", type: "status" },
		{ key: "presenting_complaint", label: "Complaint" },
		{ key: "treatment_plan_text", label: "Treatment Plan Summary" },
	],
	vitals: [
		{ key: "timestamp", label: "Recorded On", type: "datetime" },
		{ key: "temperature", label: "Temperature" },
		{ key: "weight", label: "Weight" },
		{ key: "heart_rate", label: "Heart Rate" },
		{ key: "respiratory_rate", label: "Respiratory Rate" },
		{ key: "body_condition_score", label: "Body Condition" },
		{ key: "service_branch", label: "Branch" },
	],
	diagnoses: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "diagnosis", label: "Diagnosis" },
		{ key: "diagnosis_type", label: "Type" },
		{ key: "practitioner", label: "Practitioner" },
		{ key: "service_branch", label: "Branch" },
	],
	symptoms: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "symptom", label: "Symptom" },
		{ key: "practitioner", label: "Practitioner" },
		{ key: "service_branch", label: "Branch" },
	],
	treatments: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "item", label: "Item" },
		{ key: "qty", label: "Qty" },
		{ key: "uom", label: "UOM" },
		{ key: "practitioner", label: "Practitioner" },
		{ key: "service_branch", label: "Branch" },
	],
	vaccinations: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "vaccine", label: "Vaccine" },
		{ key: "administered_by_name", label: "Practitioner" },
		{ key: "service_branch", label: "Branch" },
		{ key: "status", label: "Status", type: "status" },
		{ key: "next_due_date", label: "Next Due" },
	],
	labs: [
		{ key: "timestamp", label: "Requested On", type: "datetime" },
		{ key: "name", label: "Order" },
		{ key: "status", label: "Status", type: "status" },
		{ key: "tests_summary", label: "Tests" },
		{ key: "results_summary", label: "Results" },
		{ key: "service_branch", label: "Branch" },
	],
});

function today() {
	return frappe.datetime?.get_today?.() || new Date().toISOString().slice(0, 10);
}

function addDays(date, days) {
	if (frappe.datetime?.add_days) return frappe.datetime.add_days(date, days);
	const value = new Date(`${date}T00:00:00`);
	value.setDate(value.getDate() + days);
	return value.toISOString().slice(0, 10);
}

function stripHtml(value) {
	if (!value) return "";
	const container = document.createElement("div");
	container.innerHTML = String(value);
	container.querySelectorAll("script, style, iframe, object, embed, link, meta").forEach((node) => node.remove());
	return (container.textContent || container.innerText || "").replace(/\s+/g, " ").trim();
}

export default {
	name: "VeterinaryMedicalHistory",
	data() {
		const toDate = today();
		return {
			identity: window.frappe?.boot?.edgesuite_ui_identity?.veterinary || window.frappe?.boot?.vetedge_ui_identity || {},
			filters: { patient: "", from_date: addDays(toDate, -90), to_date: toDate },
			patientLabel: "",
			loading: false,
			error: "",
			data: {},
			activeTrend: "temperature",
			activeHistory: "consultations",
			trendTabs: TREND_TABS,
			historyTabs: HISTORY_TABS,
			chart: null,
		};
	},
	computed: {
		branchName() { return this.data?.summary?.default_branch || window.frappe?.boot?.edgesuite_product_menu?.branch || ""; },
		userName() { return window.frappe?.boot?.user?.full_name || window.frappe?.session?.user_fullname || window.frappe?.session?.user || ""; },
		summary() { return this.data?.summary || {}; },
		activeTrendRows() { return this.data?.trends?.[this.activeTrend] || []; },
		activeHistoryColumns() { return COLUMNS[this.activeHistory] || []; },
		activeHistoryRows() { return this.prepareRows(this.activeHistory, this.rowsFor(this.activeHistory)); },
	},
	watch: {
		activeTrend() { this.$nextTick(() => this.renderTrendChart()); },
	},
	mounted() {
		const params = new URLSearchParams(window.location.search || "");
		const routePatient = window.frappe?.route_options?.patient || params.get("patient") || "";
		if (routePatient) {
			this.filters.patient = routePatient;
			this.patientLabel = routePatient;
			if (window.frappe?.route_options) window.frappe.route_options = null;
			this.load();
		}
	},
	beforeUnmount() {
		this.clearChart();
	},
	methods: {
		async searchPatients(term) {
			const response = await frappe.call("frappe.desk.search.search_link", {
				doctype: "Veterinary Patient",
				txt: term || "",
				page_length: 20,
				filters: JSON.stringify({ status: ["!=", "Deceased"] }),
			});
			return (response.message || []).map((row) => ({
				value: row.value || row.name,
				label: row.description || row.label || row.value || row.name,
				description: row.value || row.name,
			}));
		},
		selectPatient(value) {
			this.filters.patient = value || "";
			this.patientLabel = value || "";
			this.data = {};
			this.error = "";
			if (value) this.load();
		},
		resetDates() {
			const toDate = today();
			this.filters.from_date = addDays(toDate, -90);
			this.filters.to_date = toDate;
			if (this.filters.patient) this.load();
		},
		async load() {
			if (!this.filters.patient || this.loading) return;
			this.loading = true;
			this.error = "";
			try {
				const response = await frappe.call(API.history, {
					patient: this.filters.patient,
					from_date: this.filters.from_date || undefined,
					to_date: this.filters.to_date || undefined,
					limit: 100,
				});
				this.data = response.message || {};
				this.patientLabel = this.data?.summary?.patient_name || this.filters.patient;
				this.activeTrend = this.firstAvailableTrend();
				this.activeHistory = this.firstAvailableHistory();
				const url = new URL(window.location.href);
				url.pathname = "/app/veterinary-medical-history";
				url.search = new URLSearchParams({ patient: this.filters.patient }).toString();
				window.history.replaceState({}, "", url);
				await this.$nextTick();
				this.renderTrendChart();
			} catch (error) {
				this.data = {};
				this.error = error?.message || error?._server_messages || __("Medical history could not be loaded.");
			} finally {
				this.loading = false;
			}
		},
		firstAvailableTrend() {
			return TREND_TABS.find((tab) => (this.data?.trends?.[tab.value] || []).length)?.value || "temperature";
		},
		firstAvailableHistory() {
			return HISTORY_TABS.find((tab) => this.rowsFor(tab.value).length)?.value || "consultations";
		},
		rowsFor(section) { return this.data?.[section] || []; },
		prepareRows(section, rows) {
			if (section !== "consultations") return rows;
			return rows.map((row) => ({
				...row,
				treatment_plan_text: stripHtml(row.treatment_plan_summary) || "—",
			}));
		},
		clearChart() {
			this.chart = null;
			const target = this.$refs.trendChart;
			if (target) target.innerHTML = "";
		},
		renderTrendChart() {
			const target = this.$refs.trendChart;
			const rows = this.activeTrendRows;
			if (!target || !rows.length) return;
			target.innerHTML = "";
			const label = TREND_TABS.find((tab) => tab.value === this.activeTrend)?.label || this.activeTrend;
			if (typeof frappe.Chart !== "function") {
				target.innerHTML = `<div class="history-chart-empty">${__("Chart runtime is unavailable.")}</div>`;
				return;
			}
			this.chart = new frappe.Chart(target, {
				title: `${label} Trend`,
				data: {
					labels: rows.map((row) => frappe.datetime?.str_to_user?.(row.timestamp) || row.timestamp),
					datasets: [{ name: label, values: rows.map((row) => Number(row.value || 0)) }],
				},
				type: "line",
				height: 260,
				lineOptions: { hideDots: 0 },
			});
		},
		openHistoryRow(row) {
			if (!row) return;
			if (this.activeHistory === "consultations" && row.name) {
				window.location.assign(`/app/vetedge-clinical-workspace?consultation=${encodeURIComponent(row.name)}`);
				return;
			}
			if (this.activeHistory === "labs" && row.name) {
				frappe.set_route("Form", "Veterinary Lab Order", row.name);
				return;
			}
			if (this.activeHistory === "vaccinations" && (row.name || row.vaccination)) {
				frappe.set_route("Form", "Veterinary Vaccination Record", row.name || row.vaccination);
			}
		},
		formatDateTime(value) { return value ? frappe.datetime?.str_to_user?.(value) || value : ""; },
		displayValue(value) { return value === undefined || value === null || value === "" ? "—" : value; },
		openRoute(route) {
			if (!route) return;
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge");
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
	},
};
</script>

<style scoped>
.history-filter-grid{display:grid;grid-template-columns:minmax(16rem,1.5fr) repeat(2,minmax(10rem,.7fr));gap:.75rem;width:100%}.history-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;margin-bottom:1rem}.history-patient-card,.history-summary-card{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);display:grid;gap:.25rem;padding:1rem}.history-patient-card{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-100,#d9edff)}.history-patient-card span,.history-summary-card span{color:var(--edge-color-ink-500,#617589);font-size:.72rem;font-weight:700;text-transform:uppercase}.history-patient-card strong,.history-summary-card strong{color:var(--edge-color-ink-900,#172b3a);font-size:1rem}.history-patient-card small{color:var(--edge-color-ink-500,#617589)}.history-card{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem);margin-bottom:1rem;padding:1rem}.history-card-header{align-items:flex-start;display:flex;gap:1rem;justify-content:space-between;margin-bottom:1rem}.history-card-header h2{font-size:1.05rem;margin:.1rem 0 .25rem}.history-card-header p{color:var(--edge-color-ink-500,#617589);margin:0}.history-period{background:var(--edge-color-surface-muted,#f6f8fa);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:999px;color:var(--edge-color-ink-600,#526579);font-size:.75rem;padding:.4rem .7rem;white-space:nowrap}.history-tabs{display:flex;gap:.4rem;overflow-x:auto;padding-bottom:.25rem}.history-tab{align-items:center;background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:999px;color:var(--edge-color-ink-600,#526579);cursor:pointer;display:flex;gap:.4rem;padding:.5rem .8rem;white-space:nowrap}.history-tab.is-active{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-500,#1677c8);color:var(--edge-color-brand-700,#0c4f87);font-weight:700}.history-tab small{align-items:center;background:var(--edge-color-surface-muted,#f6f8fa);border-radius:999px;display:inline-flex;font-size:.68rem;height:1.25rem;justify-content:center;min-width:1.25rem;padding:0 .3rem}.history-chart-shell{border-top:1px solid var(--edge-color-border,#dfe6ec);margin-top:.8rem;min-height:18rem;padding-top:1rem}.history-chart{min-height:17rem;width:100%}.history-chart-empty{align-items:center;border:1px dashed var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);color:var(--edge-color-ink-500,#617589);display:flex;justify-content:center;min-height:14rem;padding:1rem}.history-tabs--records{margin-bottom:1rem}@media(max-width:60rem){.history-filter-grid{grid-template-columns:1fr 1fr}.history-filter-grid>*:first-child{grid-column:1/-1}.history-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:40rem){.history-filter-grid,.history-summary{grid-template-columns:1fr}.history-filter-grid>*:first-child{grid-column:auto}.history-card-header{flex-direction:column}.history-period{white-space:normal}}
</style>