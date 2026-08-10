<template>
	<EdgeModal
		:open="openState"
		title="Patient Medical History"
		:subtitle="subtitle"
		:busy="loading"
		@close="close"
	>
		<EdgeLoadingState v-if="loading" message="Loading medical history..." :skeleton="true" />
		<EdgeErrorState
			v-else-if="error"
			title="Medical history could not load"
			:message="error"
			action-label="Try again"
			@retry="load"
		/>
		<div v-else class="history-modal">
			<section class="history-modal-filters">
				<EdgeInput v-model="fromDate" type="date" label="From Date" />
				<EdgeInput v-model="toDate" type="date" label="To Date" />
				<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="load">Apply</button>
				<button type="button" class="edge-button" :disabled="loading" @click="resetDates">Last 90 Days</button>
			</section>

			<section class="history-modal-summary">
				<div class="history-modal-summary-card history-modal-summary-card--patient">
					<span>Patient</span>
					<strong>{{ summary.patient_name || summary.patient || patient }}</strong>
					<small>{{ [summary.species, summary.breed].filter(Boolean).join(' · ') || 'Veterinary Patient' }}</small>
				</div>
				<div class="history-modal-summary-card"><span>Pet Owner</span><strong>{{ summary.primary_owner || '—' }}</strong></div>
				<div class="history-modal-summary-card"><span>Latest Weight</span><strong>{{ displayValue(summary.latest_weight) }}</strong></div>
				<div class="history-modal-summary-card"><span>Latest Temperature</span><strong>{{ displayValue(summary.latest_temperature) }}</strong></div>
			</section>

			<section class="history-modal-card">
				<header class="history-modal-header">
					<div><strong>Vitals Trends</strong><small>Longitudinal vital-sign changes for the selected period.</small></div>
				</header>
				<nav class="history-modal-tabs" aria-label="Vitals trend charts">
					<button
						v-for="tab in trendTabs"
						:key="tab.value"
						type="button"
						:class="['history-modal-tab', { 'is-active': activeTrend === tab.value }]"
						@click="activeTrend = tab.value"
					>
						{{ tab.label }}
					</button>
				</nav>
				<div class="history-modal-chart-shell">
					<div v-if="!activeTrendRows.length" class="history-modal-empty">No chart data in this range.</div>
					<div v-else ref="trendChart" class="history-modal-chart"></div>
				</div>
			</section>

			<section class="history-modal-card">
				<header class="history-modal-header">
					<div><strong>Medical History</strong><small>Review the patient's longitudinal clinical record by source.</small></div>
				</header>
				<nav class="history-modal-tabs history-modal-tabs--records" aria-label="Medical history sections">
					<button
						v-for="tab in historyTabs"
						:key="tab.value"
						type="button"
						:class="['history-modal-tab', { 'is-active': activeHistory === tab.value }]"
						@click="activeHistory = tab.value"
					>
						<span>{{ tab.label }}</span><small>{{ rowsFor(tab.value).length }}</small>
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
		</div>
		<template #footer>
			<button type="button" class="edge-button" :disabled="loading" @click="close">Close</button>
		</template>
	</EdgeModal>
</template>

<script>
const API = "vetedge.services.medical_history.get_patient_medical_history_view";
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
	],
	vitals: [
		{ key: "timestamp", label: "Recorded On", type: "datetime" },
		{ key: "temperature", label: "Temperature" },
		{ key: "weight", label: "Weight" },
		{ key: "heart_rate", label: "Heart Rate" },
		{ key: "respiratory_rate", label: "Respiratory Rate" },
		{ key: "body_condition_score", label: "Body Condition" },
	],
	diagnoses: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "diagnosis", label: "Diagnosis" },
		{ key: "diagnosis_type", label: "Type" },
		{ key: "practitioner", label: "Practitioner" },
	],
	symptoms: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "symptom", label: "Symptom" },
		{ key: "practitioner", label: "Practitioner" },
	],
	treatments: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "item", label: "Item" },
		{ key: "qty", label: "Qty" },
		{ key: "uom", label: "UOM" },
		{ key: "practitioner", label: "Practitioner" },
	],
	vaccinations: [
		{ key: "timestamp", label: "Date/Time", type: "datetime" },
		{ key: "vaccine", label: "Vaccine" },
		{ key: "administered_by_name", label: "Practitioner" },
		{ key: "status", label: "Status", type: "status" },
		{ key: "next_due_date", label: "Next Due" },
	],
	labs: [
		{ key: "timestamp", label: "Requested On", type: "datetime" },
		{ key: "name", label: "Order" },
		{ key: "status", label: "Status", type: "status" },
		{ key: "tests_summary", label: "Tests" },
		{ key: "results_summary", label: "Results" },
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

export default {
	name: "VetEdgeMedicalHistoryModal",
	data() {
		const toDate = today();
		return {
			openState: false,
			loading: false,
			error: "",
			patient: "",
			patientLabel: "",
			fromDate: addDays(toDate, -90),
			toDate,
			data: {},
			activeTrend: "temperature",
			activeHistory: "consultations",
			trendTabs: TREND_TABS,
			historyTabs: HISTORY_TABS,
			chart: null,
		};
	},
	computed: {
		summary() { return this.data?.summary || {}; },
		subtitle() { return this.summary.patient_name || this.patientLabel || this.patient || "Veterinary Patient"; },
		activeTrendRows() { return this.data?.trends?.[this.activeTrend] || []; },
		activeHistoryColumns() { return COLUMNS[this.activeHistory] || []; },
		activeHistoryRows() { return this.rowsFor(this.activeHistory); },
	},
	watch: {
		activeTrend() { this.$nextTick(() => this.renderTrendChart()); },
	},
	beforeUnmount() { this.clearChart(); },
	methods: {
		open({ patient, patientLabel = "" } = {}) {
			const value = String(patient || "").trim();
			if (!value) return;
			this.patient = value;
			this.patientLabel = patientLabel || value;
			this.openState = true;
			this.error = "";
			this.resetDates(false);
			this.load();
		},
		close() {
			if (this.loading) return;
			this.clearChart();
			this.openState = false;
			this.error = "";
			this.data = {};
		},
		resetDates(reload = true) {
			const toDate = today();
			this.fromDate = addDays(toDate, -90);
			this.toDate = toDate;
			if (reload && this.patient) this.load();
		},
		async load() {
			if (!this.patient || this.loading) return;
			this.loading = true;
			this.error = "";
			try {
				const response = await frappe.call(API, {
					patient: this.patient,
					from_date: this.fromDate || undefined,
					to_date: this.toDate || undefined,
					limit: 100,
				});
				this.data = response.message || {};
				this.activeTrend = TREND_TABS.find((tab) => (this.data?.trends?.[tab.value] || []).length)?.value || "temperature";
				this.activeHistory = HISTORY_TABS.find((tab) => this.rowsFor(tab.value).length)?.value || "consultations";
				await this.$nextTick();
				this.renderTrendChart();
			} catch (error) {
				this.data = {};
				this.error = error?.message || error?._server_messages || __("Medical history could not be loaded.");
			} finally {
				this.loading = false;
			}
		},
		rowsFor(section) { return this.data?.[section] || []; },
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
				target.innerHTML = `<div class="history-modal-empty">${__("Chart runtime is unavailable.")}</div>`;
				return;
			}
			this.chart = new frappe.Chart(target, {
				title: `${label} Trend`,
				data: {
					labels: rows.map((row) => frappe.datetime?.str_to_user?.(row.timestamp) || row.timestamp),
					datasets: [{ name: label, values: rows.map((row) => Number(row.value || 0)) }],
				},
				type: "line",
				height: 230,
				lineOptions: { hideDots: 0 },
			});
		},
		openHistoryRow(row) {
			if (!row) return;
			if (this.activeHistory === "consultations" && row.name) {
				this.close();
				window.location.assign(`/app/vetedge-clinical-workspace?consultation=${encodeURIComponent(row.name)}`);
				return;
			}
			if (this.activeHistory === "labs" && row.name) frappe.set_route("Form", "Veterinary Lab Order", row.name);
			if (this.activeHistory === "vaccinations" && (row.name || row.vaccination)) frappe.set_route("Form", "Veterinary Vaccination Record", row.name || row.vaccination);
		},
		displayValue(value) { return value === undefined || value === null || value === "" ? "—" : value; },
	},
};
</script>

<style scoped>
.history-modal{display:grid;gap:1rem;min-width:min(76vw,68rem)}.history-modal-filters{align-items:end;display:grid;gap:.75rem;grid-template-columns:repeat(2,minmax(10rem,1fr)) auto auto}.history-modal-summary{display:grid;gap:.65rem;grid-template-columns:repeat(4,minmax(0,1fr))}.history-modal-summary-card{background:var(--edge-color-surface-muted,#f6f8fa);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);display:grid;gap:.2rem;padding:.75rem}.history-modal-summary-card--patient{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-100,#d9edff)}.history-modal-summary-card span{color:var(--edge-color-ink-500,#617589);font-size:.7rem;font-weight:700;text-transform:uppercase}.history-modal-summary-card strong{color:var(--edge-color-ink-900,#172b3a)}.history-modal-summary-card small{color:var(--edge-color-ink-500,#617589)}.history-modal-card{border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem);display:grid;gap:.75rem;padding:.85rem}.history-modal-header>div{display:grid;gap:.15rem}.history-modal-header small{color:var(--edge-color-ink-500,#617589)}.history-modal-tabs{display:flex;gap:.35rem;overflow-x:auto;padding-bottom:.15rem}.history-modal-tab{align-items:center;background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:999px;color:var(--edge-color-ink-600,#526579);display:flex;gap:.35rem;padding:.4rem .7rem;white-space:nowrap}.history-modal-tab.is-active{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-500,#1677c8);color:var(--edge-color-brand-700,#0c4f87);font-weight:700}.history-modal-tab small{background:var(--edge-color-surface-muted,#f6f8fa);border-radius:999px;font-size:.65rem;padding:.05rem .3rem}.history-modal-chart-shell{min-height:15rem}.history-modal-chart{min-height:14rem}.history-modal-empty{align-items:center;border:1px dashed var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);color:var(--edge-color-ink-500,#617589);display:flex;justify-content:center;min-height:10rem;padding:1rem}@media(max-width:60rem){.history-modal{min-width:0}.history-modal-filters{grid-template-columns:1fr 1fr}.history-modal-summary{grid-template-columns:repeat(2,1fr)}}@media(max-width:40rem){.history-modal-filters,.history-modal-summary{grid-template-columns:1fr}}
</style>
