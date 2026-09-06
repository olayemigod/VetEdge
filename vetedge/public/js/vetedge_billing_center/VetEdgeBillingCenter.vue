<template>
	<EdgeAppShell product="vetedge" title="Veterinary" :tenant-name="identity.tenant_name || ''" :branch-name="branchName" :user-name="userName" :active-route="activeRoute" @navigate="openRoute">
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader :eyebrow="pageEyebrow" :title="pageTitle" :subtitle="pageSubtitle" action-label="Refresh" @action="refresh" />
			</template>

			<section v-if="!isSessionsPage" class="billing-summary">
				<EdgeStatCard label="Open Sessions" :value="summary.open_sessions || 0" icon="file-text" />
				<EdgeStatCard label="Outstanding Sessions" :value="summary.outstanding_sessions || 0" icon="circle-alert" />
				<EdgeStatCard label="Outstanding Amount" :value="formatCurrency(summary.outstanding_amount)" icon="wallet" />
				<EdgeStatCard label="Collected" :value="formatCurrency(summary.total_paid)" icon="badge-check" />
			</section>

			<template #filters>
				<EdgeFilterBar title="Filter billing sessions">
					<div class="billing-filters">
						<EdgeLinkField :model-value="filters.company" label="Company" placeholder="All visible companies" :searcher="(query) => linkSearch('company', query)" @update:model-value="(value) => setFilter('company', value)" />
						<EdgeLinkField :model-value="filters.branch" label="Branch" placeholder="All permitted branches" :searcher="(query) => linkSearch('branch', query)" @update:model-value="(value) => setFilter('branch', value)" />
						<EdgeLinkField :model-value="filters.customer" label="Customer" placeholder="All relevant customers" :searcher="(query) => linkSearch('customer', query)" @update:model-value="(value) => setFilter('customer', value)" />
						<EdgeLinkField :model-value="filters.animal" label="Patient" placeholder="Search pet name or patient ID" :searcher="(query) => linkSearch('animal', query)" @update:model-value="(value) => setFilter('animal', value)" />
						<EdgeDropdown :model-value="filters.status" label="Status" placeholder="All statuses" :options="statusOptions" @update:model-value="(value) => setFilter('status', value)" />
						<EdgeDropdown :model-value="filters.activity" label="Session Activity" placeholder="Choose session activity" :options="activityOptions" @update:model-value="(value) => setFilter('activity', value)" />
						<EdgeDropdown :model-value="datePreset" label="Date Range" placeholder="Choose date range" :options="datePresetOptions" @update:model-value="setDatePreset" />
						<EdgeInput :model-value="filters.from_date" type="date" label="From Date" @update:model-value="(value) => setDateField('from_date', value)" />
						<EdgeInput :model-value="filters.to_date" type="date" label="To Date" @update:model-value="(value) => setDateField('to_date', value)" />
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<section v-if="scope.restricted && !(scope.permitted_branches || []).length" class="billing-warning">
				<strong>No permitted billing branch</strong>
				<p>Your account has no active Branch assignment, so this page is intentionally empty. Ask an administrator to assign the appropriate Branch.</p>
			</section>

			<section v-if="filters.activity === 'actionable' && Number(summary.no_billing_activity_sessions || 0) > 0" class="billing-info">
				<strong>Actionable billing view</strong>
				<p>{{ summary.no_billing_activity_sessions }} session{{ Number(summary.no_billing_activity_sessions) === 1 ? '' : 's' }} with no charge or invoice activity {{ Number(summary.no_billing_activity_sessions) === 1 ? 'is' : 'are' }} hidden. Choose All Sessions or No Billing Activity to review them.</p>
			</section>

			<EdgeLoadingState v-if="loading" :message="isSessionsPage ? 'Loading Billing Sessions...' : 'Loading Billing Center...'" :skeleton="true" />
			<EdgeErrorState v-else-if="error" :title="isSessionsPage ? 'Billing Sessions could not load' : 'Billing Center could not load'" :message="error" action-label="Try again" @retry="refresh" />
			<template v-else>
				<section class="billing-boundary"><strong>Accounting safety</strong><p>{{ boundary }}</p></section>
				<EdgeDataTable :columns="columns" :rows="rows" :actions="rowActions" empty-title="No billing sessions" empty-description="No Veterinary Billing Sessions match the current filters." @row-click="openSession" @action="handleRowAction">
					<template #footer>
						<span>Showing {{ firstVisible }}–{{ lastVisible }} of {{ total }}</span>
						<div class="billing-pagination">
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasPrevious || loading" @click="previousPage">Previous</button>
							<button type="button" class="edge-button edge-button--compact" :disabled="!hasNext || loading" @click="nextPage">Next</button>
						</div>
					</template>
				</EdgeDataTable>
			</template>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const API = Object.freeze({
	center: 'vetedge.services.billing_center.get_billing_center',
	links: 'vetedge.services.billing_center.get_billing_center_link_options',
});
const STATUS_OPTIONS = ['Draft', 'Active', 'Partially Paid', 'Paid', 'Closed', 'Cancelled'];
const ACTIVITY_OPTIONS = Object.freeze([
	{ value: 'actionable', label: 'Actionable Billing' },
	{ value: 'all', label: 'All Sessions' },
	{ value: 'empty', label: 'No Billing Activity' },
]);
const DATE_PRESET_FALLBACK = Object.freeze([
	{ value: 'today', label: 'Today' },
	{ value: 'yesterday', label: 'Yesterday' },
	{ value: 'this_week', label: 'This Week' },
	{ value: 'last_week', label: 'Last Week' },
	{ value: 'this_month', label: 'This Month' },
	{ value: 'last_month', label: 'Last Month' },
	{ value: 'this_quarter', label: 'This Quarter' },
	{ value: 'last_quarter', label: 'Last Quarter' },
	{ value: 'this_year', label: 'This Year' },
	{ value: 'last_year', label: 'Last Year' },
	{ value: 'full_history', label: 'Full History' },
	{ value: 'custom', label: 'Custom Range' },
]);
const blankFilters = () => ({ company: '', branch: '', customer: '', animal: '', status: '', activity: 'actionable', from_date: '', to_date: '' });
const errorMessage = (error, fallback) => error?.message || error?._server_messages || error?.exc_type || fallback || __('Billing Center could not be loaded.');
const call = (method, args = {}) => frappe.call(method, args).then((response) => response?.message);
const dateRanges = () => frappe.EdgeSuite?.DateRanges || null;

export default {
	name: 'VetEdgeBillingCenter',
	data() {
		return {
			filters: blankFilters(),
			datePreset: 'full_history',
			rows: [],
			total: 0,
			start: 0,
			pageLength: 25,
			summary: {},
			scope: {},
			currency: 'NGN',
			capabilities: {},
			boundary: '',
			loading: true,
			error: '',
			columns: [
				{ key: 'name', label: 'Billing Session' },
				{ key: 'customer', label: 'Customer' },
				{ key: 'patient_display', label: 'Patient' },
				{ key: 'branch', label: 'Branch' },
				{ key: 'status', label: 'Status', type: 'status' },
				{ key: 'total_charges', label: 'Charges', type: 'currency' },
				{ key: 'total_invoiced', label: 'Invoiced', type: 'currency' },
				{ key: 'total_paid', label: 'Paid', type: 'currency' },
				{ key: 'outstanding_amount', label: 'Outstanding', type: 'currency' },
				{ key: 'latest_invoice', label: 'Latest Invoice' },
				{ key: 'payment_status', label: 'Payment Status', type: 'status' },
			],
			rowActions: [
				{ key: 'open_session', label: 'Open Session', primary: true },
				{ key: 'open_invoice', label: 'Open Latest Invoice' },
			],
		};
	},
	computed: {
		identity() { return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {}; },
		branchName() { return this.filters.branch || frappe.boot?.edgesuite_product_menu?.branch || 'All Permitted Branches'; },
		userName() { const user = frappe.session?.user || ''; const info = frappe.boot?.user_info?.[user] || {}; return info.fullname || info.full_name || user; },
		statusOptions() { return STATUS_OPTIONS.map((value) => ({ value, label: value })); },
		activityOptions() { return ACTIVITY_OPTIONS; },
		datePresetOptions() {
			const options = dateRanges()?.getOptions?.();
			return Array.isArray(options) && options.length ? options : DATE_PRESET_FALLBACK;
		},
		firstVisible() { return this.total ? this.start + 1 : 0; },
		lastVisible() { return Math.min(this.start + this.rows.length, this.total); },
		hasPrevious() { return this.start > 0; },
		hasNext() { return this.start + this.pageLength < this.total; },
		isSessionsPage() { return String(window.location?.pathname || '').replace(/\/+$/, '') === '/desk/vetedge-billing-sessions'; },
		activeRoute() { return this.isSessionsPage ? '/desk/vetedge-billing-sessions' : '/desk/vetedge-billing-center'; },
		pageEyebrow() { return 'Billing Operations'; },
		pageTitle() { return this.isSessionsPage ? 'Billing Sessions' : 'Billing Center'; },
		pageSubtitle() {
			return this.isSessionsPage
				? 'Permission-aware Veterinary Billing Session worklist with safe drill-through to authoritative accounting documents.'
				: 'Consolidated Veterinary billing visibility with safe drill-through to authoritative ERPNext accounting workflows.';
		},
	},
	mounted() { this.refresh(); },
	methods: {
		async refresh() {
			this.loading = true;
			this.error = '';
			try {
				const payload = await call(API.center, { filters: this.filters, start: this.start, page_length: this.pageLength });
				this.rows = payload?.rows || [];
				this.total = Number(payload?.total || 0);
				this.pageLength = Number(payload?.page_length || this.pageLength);
				this.summary = payload?.summary || {};
				this.scope = payload?.scope || {};
				this.currency = payload?.currency || 'NGN';
				this.capabilities = payload?.capabilities || {};
				this.boundary = payload?.boundary || '';
			} catch (error) {
				this.error = errorMessage(error);
			} finally {
				this.loading = false;
			}
		},
		setFilter(field, value) {
			this.filters[field] = value ?? '';
			if (field === 'company') {
				this.filters.branch = '';
				this.filters.customer = '';
				this.filters.animal = '';
			} else if (field === 'branch') {
				this.filters.customer = '';
				this.filters.animal = '';
			} else if (field === 'customer') {
				this.filters.animal = '';
			}
		},
		setDatePreset(value) {
			this.datePreset = value || 'full_history';
			if (this.datePreset === 'custom') return;
			const range = dateRanges()?.getRange?.(this.datePreset);
			if (!range) return;
			this.filters.from_date = range.start || '';
			this.filters.to_date = range.end || '';
		},
		setDateField(field, value) {
			this.filters[field] = value || '';
			this.datePreset = 'custom';
		},
		async linkSearch(fieldname, query) {
			return (await call(API.links, {
				fieldname,
				query,
				company: this.filters.company || undefined,
				branch: this.filters.branch || undefined,
				customer: this.filters.customer || undefined,
				activity: this.filters.activity || 'actionable',
			})) || [];
		},
		applyFilters() { this.start = 0; this.refresh(); },
		resetFilters() { this.filters = blankFilters(); this.datePreset = 'full_history'; this.start = 0; this.refresh(); },
		previousPage() { this.start = Math.max(0, this.start - this.pageLength); this.refresh(); },
		nextPage() { this.start += this.pageLength; this.refresh(); },
		formatCurrency(value) {
			const amount = Number(value || 0);
			try {
				return new Intl.NumberFormat('en-NG', {
					style: 'currency',
					currency: this.currency || 'NGN',
					currencyDisplay: 'narrowSymbol',
					minimumFractionDigits: 2,
					maximumFractionDigits: 2,
				}).format(amount);
			} catch (_error) {
				return `${this.currency || 'NGN'} ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
			}
		},
		openSession(row) { if (row?.name) frappe.set_route('Form', 'Veterinary Billing Session', row.name); },
		handleRowAction(payload) {
			const action = typeof payload?.action === 'string' ? payload.action : (payload?.action?.key || payload?.key);
			const row = payload?.row;
			if (action === 'open_invoice') {
				const invoice = row?.latest_invoice || row?.current_draft_invoice;
				if (invoice && this.capabilities.sales_invoice) frappe.set_route('Form', 'Sales Invoice', invoice);
				else frappe.show_alert({ message: __('No visible invoice is linked to this billing session.'), indicator: 'orange' });
				return;
			}
			this.openSession(row);
		},
		openRoute(route) {
			if (!route) return;
			if (window.VetEdgeNavigationRecovery?.navigate?.(route)) return;
			const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.('navigation:vetedge');
			if (adapter?.open?.(route) === true) return;
			window.location.assign(route);
		},
	},
};
</script>

<style scoped>
.billing-pagination{display:flex;flex-wrap:wrap;gap:.5rem}.billing-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem;margin-bottom:1rem}.billing-filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.75rem;width:100%}.billing-boundary,.billing-warning,.billing-info{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);margin-bottom:1rem;padding:.85rem 1rem}.billing-boundary p,.billing-warning p,.billing-info p{color:var(--edge-color-ink-500,#617589);margin:.25rem 0 0}.billing-warning{border-color:var(--edge-color-warning-400,#d99b24)}.billing-info{border-color:var(--edge-color-primary-300,#9fb4ff)}@media(max-width:64rem){.billing-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:36rem){.billing-summary{grid-template-columns:1fr}}
</style>
