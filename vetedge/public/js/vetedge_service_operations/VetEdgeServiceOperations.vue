<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:tenant-name="identity.tenant_name || ''"
		:branch-name="branchName"
		:user-name="userName"
		active-route="/app/vetedge-service-operations"
		@navigate="openRoute"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					eyebrow="Hospital & Services"
					title="Hospital & Services Operations"
					subtitle="Kennel availability, boarding stays, boarding care records and grooming sessions in one EdgeSuite workspace."
					action-label="Refresh"
					@action="load"
				/>
			</template>

			<nav class="service-tabs" aria-label="Hospital and services sections">
				<button
					v-for="tab in tabs"
					:key="tab.value"
					type="button"
					:class="['service-tab', { 'is-active': resource === tab.value }]"
					@click="selectResource(tab.value)"
				>
					<span>{{ tab.label }}</span>
					<small>{{ tab.description }}</small>
				</button>
			</nav>

			<template #filters>
				<EdgeFilterBar :title="resource === 'availability' ? 'Kennel availability filters' : 'Service record filters'">
					<div v-if="resource === 'availability'" class="service-filter-grid service-filter-grid--availability">
						<EdgeLinkField
							:model-value="filters.branch"
							:selected-label="filters.branch"
							label="Branch"
							placeholder="All accessible branches"
							:searcher="searchBranches"
							@update:model-value="(value) => filters.branch = value || ''"
						/>
						<EdgeInput v-model="filters.from_date" type="date" label="From Date" />
						<EdgeInput v-model="filters.to_date" type="date" label="To Date" />
						<EdgeLinkField
							:model-value="filters.kennel"
							:selected-label="filters.kennel"
							label="Kennel"
							placeholder="All kennels"
							:searcher="searchKennels"
							@update:model-value="(value) => filters.kennel = value || ''"
						/>
						<EdgeDropdown v-model="filters.status" label="Status" :options="availabilityStatuses" placeholder="All statuses" />
					</div>
					<div v-else class="service-filter-grid">
						<EdgeInput v-model="search" type="search" label="Search" placeholder="Name, patient, status or linked record" @keyup.enter="applySearch" />
						<EdgeLinkField
							:model-value="filters.branch"
							:selected-label="filters.branch"
							label="Branch"
							placeholder="All accessible branches"
							:searcher="searchBranches"
							@update:model-value="(value) => filters.branch = value || ''"
						/>
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="load">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Hospital & Services..." :skeleton="true" />
			<EdgeErrorState v-else-if="error" title="Hospital & Services could not load" :message="error" action-label="Try again" @retry="load" />

			<template v-else-if="resource === 'availability'">
				<section class="service-summary" aria-label="Kennel availability summary">
					<div v-for="card in availability.cards || []" :key="card.label" class="service-summary-card">
						<span>{{ card.label }}</span><strong>{{ card.value }}</strong>
					</div>
				</section>
				<section class="service-card">
					<header class="service-card-header">
						<div><h2>Kennel Availability</h2><p>Capacity, occupancy pressure and expected release dates for the selected period.</p></div>
					</header>
					<EdgeDataTable
						:columns="availabilityColumns"
						:rows="availability.rows || []"
						empty-title="No kennels match the selected filters"
						empty-description="Change the branch, kennel, status or date range and try again."
						@row-click="openKennel"
					/>
				</section>
			</template>

			<template v-else>
				<section class="service-summary" aria-label="Service record summary">
					<div class="service-summary-card"><span>Visible Records</span><strong>{{ page.total || 0 }}</strong></div>
					<div class="service-summary-card"><span>Current Page</span><strong>{{ currentPage }} / {{ totalPages }}</strong></div>
					<div class="service-summary-card"><span>Workspace</span><strong>EdgeSuite</strong></div>
				</section>
				<section class="service-card">
					<header class="service-card-header">
						<div><h2>{{ page.title || activeTab.label }}</h2><p>{{ page.subtitle || activeTab.description }}</p></div>
					</header>
					<EdgeDataTable
						:columns="page.columns || []"
						:rows="page.rows || []"
						empty-title="No matching records"
						empty-description="No records are visible for the selected resource and filters."
						@row-click="openDetail"
					/>
					<footer class="service-pagination">
						<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ page.total || 0 }}</span>
						<div>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious || loading" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext || loading" @click="nextPage">Next</button>
						</div>
					</footer>
				</section>
			</template>
		</EdgePageLayout>

		<EdgeModal :open="detail.open" :title="detail.data.title || detail.data.name || 'Service Record'" :subtitle="detailSubtitle" :busy="detail.loading || busy" size="lg" @close="closeDetail">
			<EdgeLoadingState v-if="detail.loading" message="Loading service record..." :skeleton="true" />
			<div v-else class="service-detail-grid">
				<div v-for="field in detail.data.fields || []" :key="field.key" class="service-detail-field" :class="{ 'service-detail-field--wide': isWideField(field) }">
					<span>{{ field.label }}</span><strong>{{ formatDetailValue(field) }}</strong>
				</div>
			</div>
			<template #footer>
				<button type="button" class="edge-button" :disabled="busy" @click="closeDetail">Close</button>
				<button
					v-for="action in detail.data.actions || []"
					:key="action.key"
					type="button"
					:class="['edge-button', action.primary ? 'edge-button--primary' : '', action.danger ? 'edge-button--danger' : '']"
					:disabled="busy"
					@click="runDetailAction(action)"
				>
					{{ action.label }}
				</button>
			</template>
		</EdgeModal>

		<EdgeModal :open="careDialog.open" title="New Boarding Care Record" :subtitle="careDialog.stay" :busy="busy" size="lg" @close="closeCareDialog">
			<div class="service-care-grid">
				<EdgeInput v-model="careDialog.values.care_datetime" type="datetime-local" label="Care Date/Time" required />
				<EdgeDropdown v-model="careDialog.values.care_type" label="Care Type" :options="careTypes" required />
				<EdgeDropdown v-model="careDialog.values.record_status" label="Record Status" :options="careStatuses" required />
				<EdgeDropdown v-model="careDialog.values.feeding_status" label="Feeding Status" :options="feedingStatuses" />
				<EdgeDropdown v-model="careDialog.values.appetite_status" label="Appetite Status" :options="appetiteStatuses" />
				<EdgeInput v-model="careDialog.values.food_portion_percent" type="number" label="Food Portion Consumed (%)" min="0" max="100" />
				<EdgeInput v-model="careDialog.values.water_intake_ml" type="number" label="Water Intake (ml)" min="0" />
				<EdgeDropdown v-model="careDialog.values.walk_status" label="Walk Status" :options="walkStatuses" />
				<EdgeInput v-model="careDialog.values.walk_duration_minutes" type="number" label="Walk Duration (Minutes)" min="0" />
				<EdgeDropdown v-model="careDialog.values.elimination_status" label="Elimination Status" :options="eliminationStatuses" />
				<EdgeDropdown v-model="careDialog.values.mood_status" label="Mood Status" :options="moodStatuses" />
				<EdgeDropdown v-model="careDialog.values.grooming_check_status" label="Grooming Check Status" :options="groomingStatuses" />
				<EdgeTextarea class="service-care-wide" v-model="careDialog.values.notes" label="Notes" :rows="3" />
			</div>
			<template #footer>
				<button type="button" class="edge-button" :disabled="busy" @click="closeCareDialog">Cancel</button>
				<button type="button" class="edge-button edge-button--primary" :disabled="busy" @click="saveCareRecord">Save Care Record</button>
			</template>
		</EdgeModal>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	page: "vetedge.services.service_operations.get_service_operations_page",
	detail: "vetedge.services.service_operations.get_service_operation_detail",
	care: "vetedge.services.service_operations.create_boarding_care_record",
	grooming: "vetedge.services.service_operations.transition_grooming_session",
	availability: "vetedge.services.boarding.get_kennel_availability_board_view",
});
const TABS = Object.freeze([
	{ value: "availability", label: "Kennel Availability", description: "Capacity and occupancy" },
	{ value: "boarding-stays", label: "Boarding Stays", description: "Active and completed stays" },
	{ value: "boarding-care-records", label: "Care Records", description: "Boarding care observations" },
	{ value: "grooming-sessions", label: "Grooming Sessions", description: "Grooming workflow and billing" },
]);
const optionRows = (values) => values.map((value) => ({ value, label: value }));
const toLocalDatetime = (value) => value ? String(value).replace(" ", "T").slice(0, 16) : "";
const serverDatetime = (value) => value ? String(value).replace("T", " ") : value;
const today = () => frappe.datetime?.get_today?.() || new Date().toISOString().slice(0, 10);
const addDays = (date, days) => frappe.datetime?.add_days?.(date, days) || (() => { const value = new Date(`${date}T00:00:00`); value.setDate(value.getDate() + days); return value.toISOString().slice(0, 10); })();

export default {
	name: "VetEdgeServiceOperations",
	data() {
		const params = new URLSearchParams(window.location.search || "");
		const requested = params.get("resource") || "availability";
		const resource = TABS.some((tab) => tab.value === requested) ? requested : "availability";
		const fromDate = today();
		return {
			tabs: TABS,
			resource,
			search: params.get("search") || "",
			parent: params.get("parent") || "",
			requestedName: params.get("name") || "",
			filters: { branch: "", kennel: "", status: "", from_date: fromDate, to_date: addDays(fromDate, 7) },
			loading: true,
			busy: false,
			error: "",
			start: 0,
			pageLength: 25,
			page: { title: "", subtitle: "", columns: [], rows: [], total: 0, start: 0, page_length: 25 },
			availability: { cards: [], rows: [] },
			detail: { open: false, loading: false, data: {} },
			careDialog: { open: false, stay: "", values: {} },
			availabilityColumns: [
				{ key: "kennel_name", label: "Kennel" }, { key: "branch", label: "Branch" },
				{ key: "capacity", label: "Capacity" }, { key: "current_occupancy", label: "Occupied" },
				{ key: "available_slots", label: "Available" }, { key: "status", label: "Status", type: "status" },
				{ key: "active_reference", label: "Active Booking / Stay" }, { key: "expected_check_out_date", label: "Expected Check-Out" },
			],
			availabilityStatuses: [{ value: "", label: "All Statuses" }, ...optionRows(["Available", "Reserved", "Occupied", "Full", "Out of Service / Inactive"])],
			careTypes: optionRows(["Routine Check", "Feeding", "Hydration", "Walk / Exercise", "Elimination", "Grooming Check", "Comfort / Behavior", "Check Out Prep"]),
			careStatuses: optionRows(["Completed", "Skipped", "Needs Attention"]),
			feedingStatuses: optionRows(["Not Applicable", "Offered", "Partially Eaten", "Fully Eaten", "Declined"]),
			appetiteStatuses: optionRows(["Not Assessed", "Poor", "Fair", "Good", "Excellent"]),
			walkStatuses: optionRows(["Not Applicable", "Completed", "Skipped", "Needs Attention"]),
			eliminationStatuses: optionRows(["Not Observed", "Normal", "Urinated Only", "Defecated Only", "Urinated and Defecated", "Needs Attention"]),
			moodStatuses: optionRows(["Calm", "Playful", "Anxious", "Restless", "Aggressive", "Lethargic", "Needs Attention"]),
			groomingStatuses: optionRows(["Not Applicable", "Clean", "Needs Cleaning", "Needs Attention"]),
		};
	},
	computed: {
		identity() { return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {}; },
		branchName() { return this.filters.branch || frappe.boot?.edgesuite_product_menu?.branch || "All Branches"; },
		userName() { const user = frappe.session?.user || ""; const info = frappe.boot?.user_info?.[user] || {}; return info.fullname || info.full_name || user; },
		activeTab() { return TABS.find((tab) => tab.value === this.resource) || TABS[0]; },
		currentPage() { return Math.floor((this.page.start || 0) / (this.page.page_length || this.pageLength)) + 1; },
		totalPages() { return Math.max(1, Math.ceil((this.page.total || 0) / (this.page.page_length || this.pageLength))); },
		hasPrevious() { return (this.page.start || 0) > 0; },
		hasNext() { return (this.page.start || 0) + (this.page.rows?.length || 0) < (this.page.total || 0); },
		firstVisible() { return this.page.total ? (this.page.start || 0) + 1 : 0; },
		lastVisible() { return Math.min((this.page.start || 0) + (this.page.rows?.length || 0), this.page.total || 0); },
		detailSubtitle() { return [this.detail.data.status, this.detail.data.doctype].filter(Boolean).join(" · "); },
	},
	mounted() { this.load(); },
	methods: {
		openRoute(route) { const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.("navigation:vetedge"); if (adapter?.open?.(route) === true) return; window.location.assign(route); },
		async searchLink(doctype, term) {
			const response = await frappe.call("frappe.desk.search.search_link", { doctype, txt: term || "", page_length: 20, ignore_user_permissions: 0 });
			return response.message || [];
		},
		searchBranches(term) { return this.searchLink("Branch", term); },
		searchKennels(term) { return this.searchLink("Kennel", term); },
		selectResource(resource) { this.resource = resource; this.start = 0; this.search = ""; this.parent = ""; this.requestedName = ""; this.error = ""; this.load(); },
		applySearch() { this.start = 0; this.load(); },
		resetFilters() { this.search = ""; this.parent = ""; this.filters.branch = ""; this.filters.kennel = ""; this.filters.status = ""; const fromDate = today(); this.filters.from_date = fromDate; this.filters.to_date = addDays(fromDate, 7); this.start = 0; this.load(); },
		updateLocation() {
			const params = new URLSearchParams({ resource: this.resource });
			if (this.search) params.set("search", this.search);
			if (this.parent) params.set("parent", this.parent);
			window.history.replaceState({}, "", `/app/vetedge-service-operations?${params.toString()}`);
		},
		async load() {
			if (this.loading && this.page?.rows?.length) return;
			this.loading = true; this.error = "";
			try {
				if (this.resource === "availability") await this.loadAvailability();
				else await this.loadRecords();
				this.updateLocation();
				if (this.requestedName && this.resource !== "availability") { const name = this.requestedName; this.requestedName = ""; await this.openDetail({ name }); }
			} catch (error) { this.error = error?.message || error?._server_messages || __("Hospital & Services could not be loaded."); }
			finally { this.loading = false; }
		},
		async loadAvailability() {
			const response = await frappe.call(API.availability, {
				branch: this.filters.branch || undefined,
				from_date: this.filters.from_date || undefined,
				to_date: this.filters.to_date || undefined,
				kennel: this.filters.kennel || undefined,
				status: this.filters.status || undefined,
			});
			this.availability = response.message || { cards: [], rows: [] };
		},
		async loadRecords() {
			const response = await frappe.call(API.page, { resource: this.resource, search: this.search, branch: this.filters.branch || undefined, parent: this.parent || undefined, start: this.start, page_length: this.pageLength });
			this.page = response.message || this.page;
		},
		previousPage() { this.start = Math.max(0, (this.page.start || 0) - (this.page.page_length || this.pageLength)); this.load(); },
		nextPage() { this.start = (this.page.start || 0) + (this.page.page_length || this.pageLength); this.load(); },
		async openDetail(row) {
			const name = row?.name || row;
			if (!name) return;
			this.detail = { open: true, loading: true, data: {} };
			try { const response = await frappe.call(API.detail, { resource: this.resource, name }); this.detail.data = response.message || {}; }
			catch (error) { this.error = error?.message || __("The service record could not be loaded."); this.detail.open = false; }
			finally { this.detail.loading = false; }
		},
		closeDetail() { if (!this.busy) this.detail = { open: false, loading: false, data: {} }; },
		openKennel(row) { const kennel = row?.kennel || row?.name; if (kennel) this.openRoute(`/app/vetedge-resource-center?resource=kennels&name=${encodeURIComponent(kennel)}`); },
		isWideField(field) { return ["Small Text", "Text", "Long Text"].includes(field.type); },
		formatDetailValue(field) {
			const value = field?.value;
			if (value === undefined || value === null || value === "") return "—";
			if (field.type === "Datetime") return frappe.datetime?.str_to_user?.(value) || value;
			if (field.type === "Date") return frappe.datetime?.str_to_user?.(value) || value;
			if (field.type === "Check") return Number(value) ? "Yes" : "No";
			return String(value);
		},
		async runDetailAction(action) {
			if (!action?.key || this.busy) return;
			if (action.key === "care-records") {
				const stay = this.detail.data.name; this.closeDetail(); this.resource = "boarding-care-records"; this.parent = stay; this.start = 0; return this.load();
			}
			if (action.key === "add-care-record") return this.openCareDialog(this.detail.data.name);
			if (action.key === "billing") return this.openBilling();
			const target = { "start-grooming": "In Progress", "complete-grooming": "Completed", "cancel-grooming": "Cancelled" }[action.key];
			if (!target) return;
			this.busy = true;
			try {
				const response = await frappe.call(API.grooming, { session: this.detail.data.name, status: target });
				this.detail.data = response.message || this.detail.data;
				frappe.show_alert({ message: __("Grooming session updated."), indicator: "green" });
				await this.loadRecords();
			} catch (error) { this.error = error?.message || __("Grooming session could not be updated."); }
			finally { this.busy = false; }
		},
		openBilling() {
			if (!window.vetedgeBillingModal?.open || !this.detail.data.name) { this.error = __("Billing modal helper is unavailable."); return; }
			const workspace = this;
			window.vetedgeBillingModal.open({
				doc: { doctype: "Pet Grooming Session", name: this.detail.data.name },
				is_new: () => false,
				is_dirty: () => false,
				save: async () => null,
				reload_doc: () => workspace.openDetail({ name: workspace.detail.data.name }),
			});
		},
		openCareDialog(stay) {
			this.careDialog = { open: true, stay, values: { care_datetime: toLocalDatetime(frappe.datetime?.now_datetime?.() || new Date().toISOString()), care_type: "Routine Check", record_status: "Completed", feeding_status: "Not Applicable", appetite_status: "Not Assessed", walk_status: "Not Applicable", elimination_status: "Not Observed", grooming_check_status: "Not Applicable", notes: "" } };
		},
		closeCareDialog() { if (!this.busy) this.careDialog = { open: false, stay: "", values: {} }; },
		async saveCareRecord() {
			if (this.busy || !this.careDialog.stay) return;
			if (!this.careDialog.values.care_datetime || !this.careDialog.values.care_type || !this.careDialog.values.record_status) { this.error = __("Care Date/Time, Care Type and Record Status are required."); return; }
			this.busy = true;
			try {
				const values = { ...this.careDialog.values, care_datetime: serverDatetime(this.careDialog.values.care_datetime) };
				await frappe.call(API.care, { stay: this.careDialog.stay, values });
				frappe.show_alert({ message: __("Boarding care record saved."), indicator: "green" });
				this.careDialog = { open: false, stay: "", values: {} };
				if (this.resource === "boarding-care-records") await this.loadRecords();
			} catch (error) { this.error = error?.message || __("Boarding care record could not be saved."); }
			finally { this.busy = false; }
		},
	},
};
</script>

<style scoped>
.service-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.7rem;margin-bottom:1rem}.service-tab{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);color:var(--edge-color-ink-700,#334b61);display:grid;gap:.15rem;padding:.85rem;text-align:left}.service-tab.is-active{background:var(--edge-color-brand-50,#eef7ff);border-color:var(--edge-color-brand-500,#1677c8);color:var(--edge-color-brand-700,#0c4f87)}.service-tab span{font-weight:700}.service-tab small{color:var(--edge-color-ink-500,#617589)}.service-filter-grid{display:grid;grid-template-columns:minmax(15rem,2fr) minmax(12rem,1fr);gap:.75rem;width:100%}.service-filter-grid--availability{grid-template-columns:repeat(5,minmax(9rem,1fr))}.service-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.75rem;margin-bottom:1rem}.service-summary-card{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem);display:grid;gap:.25rem;padding:1rem}.service-summary-card span{color:var(--edge-color-ink-500,#617589);font-size:.72rem;font-weight:700;text-transform:uppercase}.service-summary-card strong{font-size:1.45rem}.service-card{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-lg,1rem);display:grid;gap:1rem;padding:1rem}.service-card-header h2,.service-card-header p{margin:0}.service-card-header p{color:var(--edge-color-ink-500,#617589);margin-top:.25rem}.service-pagination{align-items:center;display:flex;justify-content:space-between}.service-pagination div{display:flex;gap:.5rem}.service-detail-grid,.service-care-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.75rem}.service-detail-field{background:var(--edge-color-surface-muted,#f6f8fa);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);display:grid;gap:.2rem;padding:.75rem}.service-detail-field span{color:var(--edge-color-ink-500,#617589);font-size:.7rem;font-weight:700;text-transform:uppercase}.service-detail-field strong{white-space:pre-wrap;word-break:break-word}.service-detail-field--wide,.service-care-wide{grid-column:1/-1}@media(max-width:70rem){.service-tabs{grid-template-columns:repeat(2,minmax(0,1fr))}.service-filter-grid--availability{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:48rem){.service-tabs,.service-filter-grid,.service-filter-grid--availability,.service-detail-grid,.service-care-grid{grid-template-columns:1fr}.service-pagination{align-items:stretch;flex-direction:column;gap:.75rem}}
</style>
