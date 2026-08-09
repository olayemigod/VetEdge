import { h } from 'vue';

import LegacyStockExpiryMonitor from './vetedge_stock_expiry_monitor/VetedgeStockExpiryMonitor.vue';

function createCanonicalStockExpiryMonitor(runtime) {
	const components = runtime?.components || runtime || {};
	const {
		EdgeAppShell,
		EdgePageLayout,
		EdgePageHeader,
		EdgeFilterBar,
		EdgeStatCard,
		EdgeDataTable,
		EdgeLoadingState,
		EdgeEmptyState,
		EdgeErrorState,
	} = components;

	const required = {
		EdgeAppShell,
		EdgePageLayout,
		EdgePageHeader,
		EdgeFilterBar,
		EdgeStatCard,
		EdgeDataTable,
		EdgeLoadingState,
		EdgeEmptyState,
		EdgeErrorState,
	};
	const missing = Object.entries(required)
		.filter(([, component]) => !component)
		.map(([name]) => name);
	if (missing.length) {
		throw new Error(`Missing EdgeSuite UI report components: ${missing.join(', ')}`);
	}

	const reportColumns = [
		{ fieldname: 'item_code', label: 'Item Code' },
		{ fieldname: 'item_name', label: 'Item Name' },
		{ fieldname: 'batch_no', label: 'Batch No' },
		{ fieldname: 'warehouse', label: 'Warehouse' },
		{ fieldname: 'quantity_display', label: 'Quantity' },
		{ fieldname: 'expiry_date_display', label: 'Expiry Date' },
		{ fieldname: 'days_left_display', label: 'Days Left' },
		{ fieldname: 'risk_status', label: 'Risk Status', status: true },
		{ fieldname: 'branch_display', label: 'Branch' },
	];
	const rowActions = [
		{ key: 'item', label: 'Open Item' },
		{ key: 'batch', label: 'Open Batch' },
	];

	function filterField(label, control) {
		return h('div', { class: 'edge-field filter-group' }, [
			h('label', { class: 'edge-field-label filter-label' }, label),
			control,
		]);
	}

	function option(value, label) {
		return h('option', { value }, label);
	}

	return {
		...LegacyStockExpiryMonitor,
		name: 'VetedgeStockExpiryMonitor',
		components: {},
		render() {
			const reportRows = (this.rows || []).map((row) => ({
				...row,
				quantity_display: `${this.formatQty(row.qty)}${row.stock_uom ? ` ${row.stock_uom}` : ''}`,
				expiry_date_display: this.formatDate(row.expiry_date) || '--',
				days_left_display: this.formatDays(row.days_to_expiry),
				risk_status: row.expiry_status || 'Unknown',
				branch_display: row.branch || '--',
			}));

			const filters = h(EdgeFilterBar, { title: 'Filter Records' }, {
				default: () => h('div', { class: 'edge-filter-grid' }, [
					filterField('Warehouse', h('select', {
						class: 'edge-select filter-select',
						value: this.filters.warehouse,
						disabled: this.metadataLoading,
						onChange: (event) => {
							this.filters.warehouse = event.target.value;
							this.fetchData();
						},
					}, [option('', 'All Warehouses'), ...(this.warehouses || []).map((value) => option(value, value))])),
					filterField('Item Group', h('select', {
						class: 'edge-select filter-select',
						value: this.filters.item_group,
						disabled: this.metadataLoading,
						onChange: (event) => {
							this.filters.item_group = event.target.value;
							this.fetchData();
						},
					}, [option('', 'All Item Groups'), ...(this.itemGroups || []).map((value) => option(value, value))])),
					filterField('Expiry Window', h('select', {
						class: 'edge-select filter-select',
						value: this.filters.expiry_window,
						disabled: this.metadataLoading,
						onChange: (event) => {
							this.filters.expiry_window = event.target.value;
							this.fetchData();
						},
					}, [option('all', 'All Inventory'), option('expired', 'Expired Batches'), option('expiring soon', 'Expiring Soon')])),
					filterField('Days Threshold', h('select', {
						class: 'edge-select filter-select',
						value: this.filters.days_threshold,
						disabled: this.metadataLoading,
						onChange: (event) => {
							this.filters.days_threshold = Number(event.target.value);
							this.fetchData();
						},
					}, [30, 60, 90, 180].map((days) => option(days, `${days} Days`)))),
					filterField('Item Code', h('input', {
						type: 'text',
						class: 'edge-input filter-input',
						value: this.filters.item,
						placeholder: 'Enter Item Code',
						disabled: this.metadataLoading,
						onInput: (event) => { this.filters.item = event.target.value; },
						onChange: () => this.fetchData(),
					})),
					h('div', { class: 'edge-field filter-group filter-action-group' }, [
						h('label', { class: 'edge-field-label filter-label', style: 'visibility:hidden' }, 'Action'),
						h('button', {
							type: 'button',
							class: 'edge-button edge-button--primary filter-btn primary',
							disabled: this.metadataLoading || this.loading,
							onClick: () => this.fetchData(),
						}, 'Apply / Refresh'),
					]),
				]),
			});

			let reportBody;
			if (this.error) {
				reportBody = h(EdgeErrorState, {
					title: 'Inventory Fetch Failed',
					message: this.error,
					onRetry: () => this.fetchData(),
				});
			} else if (this.loading) {
				reportBody = h(EdgeLoadingState, {
					message: 'Fetching batch inventory data...',
					skeleton: true,
				});
			} else {
				const statCards = [
					['Expired Batches', this.summary.expired_items || 0, 'close', 'danger', 'Total number of batches whose expiry date has passed'],
					['Expiring Soon', this.summary.expiring_soon || 0, 'activity', 'warning', 'Total number of batches expiring within the selected threshold window'],
					['Affected Total Qty', this.formatQty(this.summary.affected_qty), 'layers', 'neutral', 'Sum of quantities for all expired and expiring soon batches'],
					['Affected Warehouses', this.summary.affected_warehouses || 0, 'building', 'neutral', 'Number of distinct warehouses carrying expired or expiring stock'],
					['Highest Risk Items', this.summary.highest_risk_items || 0, 'shield', 'danger', 'Count of unique items with at least one fully expired batch'],
					['Last Recalculated', this.formatTime(this.summary.last_updated), 'activity', 'neutral', 'Time of the last server-side stock execution query'],
				].map(([label, value, icon, tone, tooltip]) => h(EdgeStatCard, { label, value, icon, tone, tooltip }));

				const table = reportRows.length
					? h(EdgeDataTable, {
						columns: reportColumns,
						rows: reportRows,
						rowKey: 'batch_no',
						actions: rowActions,
						onRowClick: (row) => row.batch_no && this.openDoc('Batch', row.batch_no),
						onAction: ({ action, row }) => {
							if (action?.key === 'item') this.openDoc('Item', row.item_code);
							if (action?.key === 'batch') this.openDoc('Batch', row.batch_no);
						},
					}, {
						footer: () => h('div', { class: 'pagination-footer' }, [
							h('span', { class: 'page-info' }, `Showing page ${this.currentPage} (${reportRows.length} of ${this.totalCount} records)`),
							h('div', { class: 'pagination-buttons' }, [
								h('button', {
									type: 'button',
									class: 'edge-button edge-button--compact pagination-btn',
									disabled: this.currentPage === 1,
									onClick: () => this.changePage(-1),
								}, 'Previous'),
								h('button', {
									type: 'button',
									class: 'edge-button edge-button--compact pagination-btn',
									disabled: this.currentPage * this.filters.limit >= this.totalCount,
									onClick: () => this.changePage(1),
								}, 'Next'),
							]),
						]),
					})
					: h(EdgeEmptyState, {
						title: 'No Expiry Records',
						description: 'No inventory batch expiries match the current filters.',
						icon: 'check',
					});

				reportBody = h('div', { class: 'edge-report-body' }, [
					h('div', { class: 'edge-stat-grid summary-stats-grid' }, statCards),
					table,
				]);
			}

			return h(EdgeAppShell, {
				product: 'vetedge',
				activeRoute: '/app/stock-expiry-monitor',
				title: 'Veterinary',
				tenantName: this.tenantName,
				branchName: this.branchName,
				userName: this.userName,
				showSidebar: false,
			}, {
				default: () => h(EdgePageLayout, null, {
					header: () => h(EdgePageHeader, {
						title: 'Stock Expiry Monitor',
						subtitle: 'Track soon-to-expire batch stock and optimize inventory safety windows',
					}),
					default: () => [filters, reportBody],
				}),
			});
		},
	};
}

function getEdgeSuiteRuntime() {
	return window.EdgeSuiteUI || window.EdgeUI || null;
}

export function mountVetedgeStockExpiryMonitor(target) {
	const runtime = getEdgeSuiteRuntime();
	if (!runtime || typeof runtime.createEdgeApp !== 'function') {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	const component = createCanonicalStockExpiryMonitor(runtime);
	const app = runtime.createEdgeApp(component);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	const runtime = getEdgeSuiteRuntime();
	window.VetedgeStockExpiryMonitor = runtime
		? createCanonicalStockExpiryMonitor(runtime)
		: LegacyStockExpiryMonitor;
	window.mountVetedgeStockExpiryMonitor = mountVetedgeStockExpiryMonitor;
}

export { createCanonicalStockExpiryMonitor };
export default LegacyStockExpiryMonitor;
