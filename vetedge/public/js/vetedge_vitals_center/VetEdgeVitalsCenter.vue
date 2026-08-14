<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/desk/veterinary-vital-signs"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Clinical Operations"
					title="Vital Signs"
					subtitle="Review recorded patient vitals and update safe clinical measurements without leaving EdgeSuite."
					action-label="Refresh"
					@action="load"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar title="Vital signs filters">
					<div class="vitals-filter-grid">
						<EdgeLinkField
							:model-value="filters.patient"
							:selected-label="filters.patient"
							label="Veterinary Patient"
							placeholder="All patients"
							:searcher="(query) => searchLink('Veterinary Patient', query)"
							@update:model-value="(value) => filters.patient = value || ''"
						/>
						<EdgeLinkField
							:model-value="filters.branch"
							:selected-label="filters.branch"
							label="Branch"
							placeholder="All permitted branches"
							:searcher="(query) => searchLink('Branch', query)"
							@update:model-value="(value) => filters.branch = value || ''"
						/>
						<EdgeInput v-model="filters.from_date" type="date" label="From Date" />
						<EdgeInput v-model="filters.to_date" type="date" label="To Date" />
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<section class="vitals-summary" aria-label="Vital signs summary">
				<EdgeStatCard label="Visible records" :value="total" tone="primary" />
				<EdgeStatCard label="Current page" :value="`${currentPage} of ${totalPages}`" tone="info" />
				<EdgeStatCard label="Date range" :value="rangeLabel" tone="neutral" />
			</section>

			<EdgeLoadingState v-if="loading" message="Loading vital signs..." :skeleton="true" />
			<EdgeErrorState v-else-if="error" title="Vital signs could not load" :message="error" action-label="Try again" @retry="load" />
			<EdgeEmptyState
				v-else-if="!rows.length"
				title="No vital signs found"
				description="No records match the selected patient, branch and date range."
			/>
			<EdgeDataTable
				v-else
				:columns="columns"
				:rows="rows"
				row-key="name"
				empty-title="No vital signs found"
				@row-click="openRecord"
			>
				<template #footer>
					<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ total }}</span>
					<div class="vitals-page-actions">
						<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious || loading" @click="previousPage">Previous</button>
						<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext || loading" @click="nextPage">Next</button>
					</div>
				</template>
			</EdgeDataTable>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const PAGE_LENGTH = 25;
const COLUMNS = Object.freeze([
	{ fieldname: "name", label: "Vital Signs" },
	{ fieldname: "patient", label: "Patient" },
	{ fieldname: "recorded_on", label: "Recorded On", fieldtype: "Datetime" },
	{ fieldname: "temperature", label: "Temperature" },
	{ fieldname: "weight", label: "Weight" },
	{ fieldname: "heart_rate", label: "Heart Rate" },
	{ fieldname: "respiratory_rate", label: "Respiratory Rate" },
	{ fieldname: "service_branch", label: "Branch" },
]);

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
	name: "VetEdgeVitalsCenter",
	data() {
		const toDate = today();
		const params = new URLSearchParams(window.location.search || "");
		return {
			loading: false,
			error: "",
			rows: [],
			total: 0,
			start: 0,
			pageLength: PAGE_LENGTH,
			columns: COLUMNS,
			filters: {
				patient: params.get("patient") || "",
				branch: params.get("branch") || "",
				from_date: params.get("from_date") || addDays(toDate, -90),
				to_date: params.get("to_date") || toDate,
			},
			requestedName: params.get("name") || "",
		};
	},
	computed: {
		identity() { return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {}; },
		branchName() { return this.filters.branch || frappe.boot?.edgesuite_product_menu?.branch || frappe.defaults?.get_user_default?.("branch") || "All Branches"; },
		userName() {
			const user = frappe.session?.user || "";
			const info = frappe.boot?.user_info?.[user] || {};
			return info.fullname || info.full_name || user;
		},
		currentPage() { return Math.floor(this.start / this.pageLength) + 1; },
		totalPages() { return Math.max(1, Math.ceil(this.total / this.pageLength)); },
		hasPrevious() { return this.start > 0; },
		hasNext() { return this.start + this.rows.length < this.total; },
		firstVisible() { return this.total ? this.start + 1 : 0; },
		lastVisible() { return Math.min(this.start + this.rows.length, this.total); },
		rangeLabel() { return `${this.filters.from_date || "Any"} → ${this.filters.to_date || "Any"}`; },
	},
	async mounted() {
		await this.load();
		if (this.requestedName) {
			window.setTimeout(() => this.openRecord({ name: this.requestedName }), 0);
		}
	},
	methods: {
		buildFilters() {
			const filters = {};
			if (this.filters.patient) filters.patient = this.filters.patient;
			if (this.filters.branch) filters.service_branch = this.filters.branch;
			if (this.filters.from_date && this.filters.to_date) {
				filters.recorded_on = ["between", [`${this.filters.from_date} 00:00:00`, `${this.filters.to_date} 23:59:59`]];
			} else if (this.filters.from_date) {
				filters.recorded_on = [">=", `${this.filters.from_date} 00:00:00`];
			} else if (this.filters.to_date) {
				filters.recorded_on = ["<=", `${this.filters.to_date} 23:59:59`];
			}
			return filters;
		},
		async load() {
			if (this.loading) return;
			this.loading = true;
			this.error = "";
			try {
				const filters = this.buildFilters();
				const [listResponse, countResponse] = await Promise.all([
					frappe.call("frappe.client.get_list", {
						doctype: "Veterinary Vital Signs",
						fields: COLUMNS.map((column) => column.fieldname),
						filters,
						order_by: "recorded_on desc",
						limit_start: this.start,
						limit_page_length: this.pageLength,
					}),
					frappe.call("frappe.client.get_count", {
						doctype: "Veterinary Vital Signs",
						filters,
					}),
				]);
				this.rows = listResponse.message || [];
				this.total = Number(countResponse.message || 0);
				this.updateLocation();
			} catch (error) {
				this.rows = [];
				this.total = 0;
				this.error = error?.message || __("Vital signs could not be loaded.");
			} finally {
				this.loading = false;
			}
		},
		applyFilters() { this.start = 0; this.load(); },
		resetFilters() {
			const toDate = today();
			this.filters = { patient: "", branch: "", from_date: addDays(toDate, -90), to_date: toDate };
			this.start = 0;
			this.load();
		},
		previousPage() { if (this.hasPrevious) { this.start = Math.max(0, this.start - this.pageLength); this.load(); } },
		nextPage() { if (this.hasNext) { this.start += this.pageLength; this.load(); } },
		async searchLink(doctype, query) {
			const response = await frappe.call("frappe.desk.search.search_link", { doctype, txt: query || "", page_length: 20, ignore_user_permissions: 0 });
			return response.message || [];
		},
		openRecord(row) {
			const name = row?.name;
			if (!name) return;
			window.VetEdgeClinicalRecordEditor?.open?.({ doctype: "Veterinary Vital Signs", name, onSaved: () => this.load() });
		},
		updateLocation() {
			const params = new URLSearchParams();
			if (this.filters.patient) params.set("patient", this.filters.patient);
			if (this.filters.branch) params.set("branch", this.filters.branch);
			if (this.filters.from_date) params.set("from_date", this.filters.from_date);
			if (this.filters.to_date) params.set("to_date", this.filters.to_date);
			window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`);
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
.vitals-filter-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem;width:100%}.vitals-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem;margin-bottom:1rem}.vitals-page-actions{display:flex;gap:.5rem}@media(max-width:64rem){.vitals-filter-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:42rem){.vitals-filter-grid,.vitals-summary{grid-template-columns:1fr}}
</style>
