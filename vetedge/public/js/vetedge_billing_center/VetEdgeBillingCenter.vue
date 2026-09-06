<template>
	<EdgeAppShell product="vetedge" title="Veterinary" :tenant-name="identity.tenant_name || ''" :branch-name="branchName" :user-name="userName" active-route="/app/vetedge-billing-center" @navigate="openRoute">
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader eyebrow="Billing Operations" title="Billing Center" subtitle="Consolidated Veterinary billing visibility with safe drill-through to authoritative ERPNext accounting workflows." action-label="Refresh" @action="refresh" />
			</template>

			<section class="billing-shortcuts" aria-label="Billing workflows">
				<button v-if="capabilities.customer" type="button" class="edge-button" @click="openList('Customer')">Customers</button>
				<button v-if="capabilities.sales_invoice" type="button" class="edge-button" @click="openList('Sales Invoice')">Sales Invoices</button>
				<button v-if="capabilities.payment_entry" type="button" class="edge-button" @click="openList('Payment Entry')">Payment Entries</button>
				<button type="button" class="edge-button" @click="openList('Veterinary Billing Session')">Billing Sessions</button>
			</section>

			<section class="billing-summary">
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
						<EdgeLinkField :model-value="filters.animal" label="Patient" placeholder="All relevant patients" :searcher="(query) => linkSearch('animal', query)" @update:model-value="(value) => setFilter('animal', value)" />
						<EdgeDropdown :model-value="filters.status" label="Status" placeholder="All statuses" :options="statusOptions" @update:model-value="(value) => setFilter('status', value)" />
						<EdgeInput v-model="filters.from_date" type="date" label="From Date" />
						<EdgeInput v-model="filters.to_date" type="date" label="To Date" />
					</div>
					<template #actions>
						<button type="button" class="edge-button edge-button--primary" :disabled="loading" @click="applyFilters">Apply</button>
						<button type="button" class="edge-button" :disabled="loading" @click="resetFilters">Reset</button>
					</template>
				</EdgeFilterBar>
			</template>

			<section v-if="scope.restricted && !(scope.permitted_branches || []).length" class="billing-warning">
				<strong>No permitted billing branch</strong>
				<p>Your account has no active Branch assignment, so Billing Center is intentionally empty. Ask an administrator to assign the appropriate Branch.</p>
			</section>

			<EdgeLoadingState v-if="loading" message="Loading Billing Center..." :skeleton="true" />
			<EdgeErrorState v-else-if="error" title="Billing Center could not load" :message="error" action-label="Try again" @retry="refresh" />
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
const blankFilters = () => ({ company: '', branch: '', customer: '', animal: '', status: '', from_date: '', to_date: '' });
const errorMessage = (error, fallback) => error?.message || error?._server_messages || error?.exc_type || fallback || __('Billing Center could not be loaded.');
const call = (method, args = {}) => frappe.call(method, args).then((response) => response?.message);

export default {
	name: 'VetEdgeBillingCenter',
	data() {
		return {
			filters: blankFilters(),
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
				{ key: 'animal', label: 'Patient' },
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
		firstVisible() { return this.total ? this.start + 1 : 0; },
		lastVisible() { return Math.min(this.start + this.rows.length, this.total); },
		hasPrevious() { return this.start > 0; },
		hasNext() { return this.start + this.pageLength < this.total; },
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
		async linkSearch(fieldname, query) {
			return (await call(API.links, { fieldname, query, company: this.filters.company || undefined, branch: this.filters.branch || undefined })) || [];
		},
		applyFilters() { this.start = 0; this.refresh(); },
		resetFilters() { this.filters = blankFilters(); this.start = 0; this.refresh(); },
		previousPage() { this.start = Math.max(0, this.start - this.pageLength); this.refresh(); },
		nextPage() { this.start += this.pageLength; this.refresh(); },
		formatCurrency(value) { return frappe.format?.(Number(value || 0), { fieldtype: 'Currency', options: this.currency }) || `${this.currency} ${Number(value || 0).toLocaleString()}`; },
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
		openList(doctype) { frappe.set_route('List', doctype); },
		openRoute(route) { if (!route) return; const adapter = (window.EdgeSuiteUI || window.EdgeUI)?.getAdapter?.('navigation:vetedge'); if (adapter?.open?.(route) === true) return; window.location.assign(route); },
	},
};
</script>

<style scoped>
.billing-shortcuts,.billing-pagination{display:flex;flex-wrap:wrap;gap:.5rem}.billing-shortcuts{margin-bottom:1rem}.billing-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem;margin-bottom:1rem}.billing-filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:.75rem;width:100%}.billing-boundary,.billing-warning{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);margin-bottom:1rem;padding:.85rem 1rem}.billing-boundary p,.billing-warning p{color:var(--edge-color-ink-500,#617589);margin:.25rem 0 0}.billing-warning{border-color:var(--edge-color-warning-400,#d99b24)}@media(max-width:64rem){.billing-summary{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:36rem){.billing-summary{grid-template-columns:1fr}}
</style>
