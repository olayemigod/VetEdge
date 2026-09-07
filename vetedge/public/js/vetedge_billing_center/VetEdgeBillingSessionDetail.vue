<template>
	<EdgeAppShell product="vetedge" title="Veterinary" :tenant-name="identity.tenant_name || ''" :branch-name="branchName" :user-name="userName" active-route="/desk/vetedge-billing-sessions" @navigate="openRoute">
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader eyebrow="Billing Operations" :title="pageTitle" :subtitle="pageSubtitle" action-label="Back to Billing Sessions" @action="backToSessions" />
			</template>

			<EdgeLoadingState v-if="loading" message="Loading Billing Session..." :skeleton="true" />
			<EdgeErrorState v-else-if="error" title="Billing Session could not load" :message="error" action-label="Back to Billing Sessions" @retry="backToSessions" />
			<template v-else>
				<section class="billing-detail-summary">
					<EdgeStatCard label="Charges" :value="formatCurrency(detail.total_charges)" icon="receipt-text" />
					<EdgeStatCard label="Invoiced" :value="formatCurrency(detail.total_invoiced)" icon="file-text" />
					<EdgeStatCard label="Paid" :value="formatCurrency(detail.total_paid)" icon="badge-check" />
					<EdgeStatCard label="Outstanding" :value="formatCurrency(detail.outstanding_amount)" icon="wallet" />
				</section>

				<section class="billing-detail-card">
					<div class="billing-detail-heading">
						<div>
							<h3>Session details</h3>
							<p>Veterinary billing context and authoritative invoice state.</p>
						</div>
						<div class="billing-detail-actions">
							<button type="button" class="edge-button" :disabled="loading" @click="refresh">Refresh</button>
							<button v-if="visibleInvoice" type="button" class="edge-button edge-button--primary" @click="openInvoice">Open Latest Invoice</button>
						</div>
					</div>
					<div class="billing-detail-grid">
						<div><span>Billing Session</span><strong>{{ detail.name || '—' }}</strong></div>
						<div><span>Customer</span><strong>{{ detail.customer || '—' }}</strong></div>
						<div><span>Patient</span><strong>{{ detail.patient_display || detail.patient_name || detail.animal || '—' }}</strong></div>
						<div><span>Branch</span><strong>{{ detail.branch || '—' }}</strong></div>
						<div><span>Status</span><strong>{{ detail.status || '—' }}</strong></div>
						<div><span>Payment Status</span><strong>{{ detail.payment_status || '—' }}</strong></div>
						<div><span>Payment Gate</span><strong>{{ detail.payment_gate_mode || '—' }}</strong></div>
						<div><span>Company</span><strong>{{ detail.company || '—' }}</strong></div>
						<div><span>Created From</span><strong>{{ sourceLabel(detail.created_from_doctype, detail.created_from_name) }}</strong></div>
						<div><span>Source Context</span><strong>{{ sourceLabel(detail.source_context_doctype, detail.source_context_name) }}</strong></div>
						<div><span>Created</span><strong>{{ formatDateTime(detail.creation) }}</strong></div>
						<div><span>Last Updated</span><strong>{{ formatDateTime(detail.modified) }}</strong></div>
					</div>
				</section>

				<section class="billing-boundary"><strong>Accounting safety</strong><p>{{ detail.boundary }}</p></section>

				<section class="billing-detail-card">
					<div class="billing-detail-heading">
						<div>
							<h3>Session charges</h3>
							<p>Charge rows recorded against this Veterinary Billing Session.</p>
						</div>
						<strong>{{ charges.length }}</strong>
					</div>
					<EdgeDataTable :columns="chargeColumns" :rows="charges" empty-title="No billing charges" empty-description="This Billing Session has no charge rows." />
				</section>
			</template>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const API = 'vetedge.services.billing_session_page.get_billing_session_detail';
const errorMessage = (error) => error?.message || error?._server_messages || error?.exc_type || __('Billing Session could not be loaded.');

export default {
	name: 'VetEdgeBillingSessionDetail',
	data() {
		return {
			detail: {},
			charges: [],
			loading: true,
			error: '',
			chargeColumns: [
				{ key: 'item_name', label: 'Item / Service' },
				{ key: 'source_name', label: 'Source' },
				{ key: 'qty', label: 'Qty' },
				{ key: 'rate', label: 'Rate', type: 'currency' },
				{ key: 'amount', label: 'Amount', type: 'currency' },
				{ key: 'billing_status', label: 'Billing Status', type: 'status' },
				{ key: 'invoice', label: 'Invoice' },
			],
		};
	},
	computed: {
		identity() { return frappe.boot?.edgesuite_ui_identity?.vetedge || frappe.boot?.vetedge_ui_identity || {}; },
		branchName() { return this.detail.branch || frappe.boot?.edgesuite_product_menu?.branch || 'All Permitted Branches'; },
		userName() { const user = frappe.session?.user || ''; const info = frappe.boot?.user_info?.[user] || {}; return info.fullname || info.full_name || user; },
		sessionName() { return new URLSearchParams(window.location.search || '').get('name') || ''; },
		pageTitle() { return this.detail.name || this.sessionName || 'Billing Session'; },
		pageSubtitle() {
			const patient = this.detail.patient_display || this.detail.patient_name || this.detail.animal;
			const context = [patient, this.detail.customer, this.detail.branch].filter(Boolean).join(' • ');
			return context || 'Veterinary Billing Session detail in the EdgeSuite Veterinary workspace.';
		},
		visibleInvoice() {
			if (!this.detail.capabilities?.sales_invoice) return '';
			return this.detail.current_draft_invoice || this.detail.latest_invoice || '';
		},
	},
	mounted() { this.refresh(); },
	methods: {
		async refresh() {
			this.loading = true;
			this.error = '';
			try {
				if (!this.sessionName) throw new Error(__('Billing Session name is missing.'));
				const response = await frappe.call(API, { name: this.sessionName });
				this.detail = response?.message || {};
				this.charges = this.detail.charges || [];
			} catch (error) {
				this.error = errorMessage(error);
			} finally {
				this.loading = false;
			}
		},
		formatCurrency(value) {
			const amount = Number(value || 0);
			const currency = this.detail.currency || 'NGN';
			try {
				return new Intl.NumberFormat('en-NG', {
					style: 'currency',
					currency,
					currencyDisplay: 'narrowSymbol',
					minimumFractionDigits: 2,
					maximumFractionDigits: 2,
				}).format(amount);
			} catch (_error) {
				return `${currency} ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
			}
		},
		formatDateTime(value) {
			if (!value) return '—';
			try { return frappe.datetime?.str_to_user ? frappe.datetime.str_to_user(value) : String(value); }
			catch (_error) { return String(value); }
		},
		sourceLabel(doctype, name) { return doctype && name ? `${doctype}: ${name}` : (name || doctype || '—'); },
		openInvoice() { if (this.visibleInvoice) frappe.set_route('Form', 'Sales Invoice', this.visibleInvoice); },
		backToSessions() { window.location.assign('/desk/vetedge-billing-sessions'); },
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
.billing-detail-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:.75rem;margin-bottom:1rem}.billing-detail-card,.billing-boundary{background:var(--edge-color-surface,#fff);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-md,.75rem);margin-bottom:1rem;padding:1rem}.billing-detail-heading{align-items:flex-start;display:flex;gap:1rem;justify-content:space-between;margin-bottom:1rem}.billing-detail-heading h3{margin:0}.billing-detail-heading p,.billing-boundary p{color:var(--edge-color-ink-500,#617589);margin:.25rem 0 0}.billing-detail-actions{display:flex;flex-wrap:wrap;gap:.5rem}.billing-detail-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.75rem}.billing-detail-grid>div{background:var(--edge-color-surface-muted,#f7f9fb);border:1px solid var(--edge-color-border,#dfe6ec);border-radius:var(--edge-radius-sm,.5rem);padding:.75rem}.billing-detail-grid span{color:var(--edge-color-ink-500,#617589);display:block;font-size:.8rem;margin-bottom:.25rem}.billing-detail-grid strong{overflow-wrap:anywhere}@media(max-width:64rem){.billing-detail-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.billing-detail-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:40rem){.billing-detail-summary,.billing-detail-grid{grid-template-columns:1fr}.billing-detail-heading{align-items:stretch;flex-direction:column}}
</style>
