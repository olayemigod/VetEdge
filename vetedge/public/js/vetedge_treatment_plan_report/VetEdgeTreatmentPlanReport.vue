<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/desk/vetedge-treatment-plan-report"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Reports"
					title="Planned Treatment"
					subtitle="Review treatment plans as a clinical report. Treatment plans belong to consultations and are not standalone billable services."
					action-label="Refresh"
					@action="load"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar title="Planned treatment filters">
					<div class="treatment-report-filters">
						<EdgeInput v-model="filters.from_date" type="date" label="From Date" />
						<EdgeInput v-model="filters.to_date" type="date" label="To Date" />
						<EdgeLinkField :model-value="filters.branch" :selected-label="filters.branch" label="Service Branch" placeholder="All permitted branches" :searcher="(query) => searchLink('Branch', query)" @update:model-value="(value) => filters.branch = value || ''" />
						<EdgeLinkField :model-value="filters.patient" :selected-label="patientLabel" label="Patient" placeholder="All patients" :searcher="(query) => searchLink('Veterinary Patient', query)" @update:model-value="(value) => filters.patient = value || ''" />
						<EdgeLinkField :model-value="filters.owner" :selected-label="filters.owner" label="Owner" placeholder="All owners" :searcher="(query) => searchLink('Customer', query)" @update:model-value="(value) => filters.owner = value || ''" />
						<EdgeLinkField :model-value="filters.practitioner" :selected-label="filters.practitioner" label="Practitioner" placeholder="All practitioners" :searcher="(query) => searchLink('User', query)" @update:model-value="(value) => filters.practitioner = value || ''" />
						<EdgeLinkField :model-value="filters.consultation_type" :selected-label="filters.consultation_type" label="Consultation Type" placeholder="All types" :searcher="(query) => searchLink('Consultation Type', query)" @update:model-value="(value) => filters.consultation_type = value || ''" />
						<EdgeLinkField :model-value="filters.item" :selected-label="filters.item" label="Treatment Item / Service" placeholder="All treatment items" :searcher="(query) => searchLink('Item', query)" @update:model-value="(value) => filters.item = value || ''" />
						<EdgeDropdown v-model="filters.consultation_status" label="Consultation Status" placeholder="All statuses" :options="statusOptions" />
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<section class="treatment-report-summary" aria-label="Planned treatment summary">
				<EdgeStatCard label="Matching rows" :value="page.total || 0" tone="primary" />
				<EdgeStatCard v-for="entry in summaryCards" :key="entry.label" :label="entry.label" :value="entry.value" :tone="tone(entry.indicator)" />
			</section>

			<EdgeLoadingState v-if="loading" message="Loading planned treatments..." :skeleton="true" />
			<EdgeErrorState v-else-if="error" title="Planned Treatment could not load" :message="error" action-label="Try again" @retry="load" />
			<EdgeDataTable
				v-else
				:columns="page.columns || []"
				:rows="page.rows || []"
				row-key="name"
				empty-title="No planned treatments"
				empty-description="No treatment-plan rows match the selected filters."
				@row-click="openRow"
			>
				<template #footer>
					<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ page.total || 0 }}</span>
					<div class="treatment-report-pagination">
						<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious || loading" @click="previousPage">Previous</button>
						<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext || loading" @click="nextPage">Next</button>
					</div>
				</template>
			</EdgeDataTable>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const PAGE_LENGTH = 50;
const STATUS_OPTIONS = Object.freeze([
	"Draft", "In Progress", "Awaiting Payment", "Pending Dispensary", "Ready for Treatment", "Completed", "Cancelled",
].map((value) => ({ value, label: value })));

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
	name: "VetEdgeTreatmentPlanReport",
	data() {
		const toDate = today();
		return {
			loading: false,
			error: "",
			start: 0,
			pageLength: PAGE_LENGTH,
			page: { columns: [], rows: [], summary: [], total: 0, start: 0, page_length: PAGE_LENGTH },
			patientLabels: {},
			statusOptions: STATUS_OPTIONS,
			filters: {
				from_date: addDays(toDate, -30),
				to_date: toDate,
				branch: "",
				patient: "",
				owner: "",
				practitioner: "",
				consultation_type: "",
				item: "",
				consultation_status: "",
			},
		};
	},
	computed: {
		identity() { return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {}; },
		branchName() { return this.filters.branch || frappe.boot?.edgesuite_product_menu?.branch || "All Branches"; },
		patientLabel() { return this.patientLabels[this.filters.patient] || this.filters.patient || ""; },
		userName() { const user = frappe.session?.user || ""; const info = frappe.boot?.user_info?.[user] || {}; return info.fullname || info.full_name || user; },
		summaryCards() { return (this.page.summary || []).slice(0, 3); },
		hasPrevious() { return this.start > 0; },
		hasNext() { return this.start + (this.page.rows?.length || 0) < (this.page.total || 0); },
		firstVisible() { return this.page.total ? this.start + 1 : 0; },
		lastVisible() { return Math.min(this.start + (this.page.rows?.length || 0), this.page.total || 0); },
	},
	mounted() { this.load(); },
	methods: {
		async load() {
			if (this.loading) return;
			this.loading = true;
			this.error = "";
			try {
				const response = await frappe.call("vetedge.services.treatment_plan_report.get_planned_treatment_view", {
					filters: this.filters,
					start: this.start,
					page_length: this.pageLength,
				});
				this.page = response.message || this.page;
			} catch (error) {
				this.error = error?.message || __("Planned Treatment could not be loaded.");
			} finally {
				this.loading = false;
			}
		},
		applyFilters() { this.start = 0; this.load(); },
		resetFilters() {
			const toDate = today();
			this.filters = { from_date: addDays(toDate, -30), to_date: toDate, branch: "", patient: "", owner: "", practitioner: "", consultation_type: "", item: "", consultation_status: "" };
			this.start = 0;
			this.load();
		},
		previousPage() { if (this.hasPrevious) { this.start = Math.max(0, this.start - this.pageLength); this.load(); } },
		nextPage() { if (this.hasNext) { this.start += this.pageLength; this.load(); } },
		async searchLink(doctype, query) {
			const response = await frappe.call("frappe.desk.search.search_link", { doctype, txt: query || "", page_length: 20, ignore_user_permissions: 0 });
			const options = response.message || [];
			if (doctype === "Veterinary Patient") {
				const labels = { ...this.patientLabels };
				for (const option of options) if (option?.value) labels[option.value] = option.label || option.description || option.value;
				this.patientLabels = labels;
			}
			return options;
		},
		tone(indicator) {
			const value = String(indicator || "").toLowerCase();
			if (value.includes("green")) return "success";
			if (value.includes("orange") || value.includes("yellow")) return "warning";
			if (value.includes("red")) return "danger";
			if (value.includes("blue")) return "info";
			return "neutral";
		},
		openRow(row) {
			const consultation = row?.consultation || row?.source_document || "";
			if (consultation) window.location.assign(`/desk/vetedge-clinical-workspace?consultation=${encodeURIComponent(consultation)}`);
		},
		openRoute(route) {
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge");
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
	},
};
</script>

<style scoped>
.treatment-report-filters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;width:100%}.treatment-report-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem;margin-bottom:1rem}.treatment-report-pagination{display:flex;gap:.5rem}@media(max-width:70rem){.treatment-report-filters{grid-template-columns:repeat(2,minmax(0,1fr))}.treatment-report-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:42rem){.treatment-report-filters,.treatment-report-summary{grid-template-columns:1fr}}
</style>