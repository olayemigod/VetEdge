<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:menuItems="menuItems"
		activeRoute="/app/vetedge-executive-dashboard"
		:tenantName="tenantName"
		:branchName="filters.branch || 'All Branches'"
		:userName="userName"
		@navigate="handleNavigation"
		data-edge-product="vetedge"
	>
		<template #notifications>
			<EdgeNotificationBell
				:unreadCount="notificationUnreadCount"
				title="Notifications"
				@toggle="toggleNotificationDrawer"
			>
				<template #icon><span class="vetedge-notification-icon" aria-hidden="true">🔔</span></template>
			</EdgeNotificationBell>
			<EdgeNotificationDrawer
				product="vetedge"
				title="Notifications"
				:open="notificationDrawerOpen"
				:notifications="filteredNotifications"
				:unreadCount="notificationUnreadCount"
				:filter="notificationFilter"
				:loading="notificationLoading"
				:error="notificationError"
				@close="notificationDrawerOpen = false"
				@update:filter="setNotificationFilter"
				@retry="fetchNotifications"
				@refresh="fetchNotifications"
				@mark-all-read="markAllNotificationsRead"
				@action="runNotificationAction"
				@open="openNotificationRoute"
			/>
		</template>

		<EdgePageLayout class="vetedge-executive-page">
			<template #header>
				<EdgePageHeader
					eyebrow="Veterinary performance"
					title="Executive Dashboard"
					subtitle="Branch-aware operational and financial performance"
					:withBackButton="false"
				/>
			</template>

			<template #filters>
				<EdgeFilterBar title="Dashboard Filters">
					<div class="vetedge-executive-filter-grid">
						<div class="edge-field">
							<label class="edge-field-label">Branch</label>
							<select v-model="filters.branch" class="edge-select edge-control" @change="applyFilters">
								<option value="">All Branches</option>
								<option v-for="branch in branches" :key="branch" :value="branch">{{ branch }}</option>
							</select>
						</div>
						<div class="edge-field">
							<label class="edge-field-label">Period</label>
							<select v-model="filters.date_preset" class="edge-select edge-control" @change="applyPreset">
								<option v-for="preset in datePresets" :key="preset.value" :value="preset.value">
									{{ preset.label }}
								</option>
							</select>
						</div>
						<div class="edge-field">
							<label class="edge-field-label">From Date</label>
							<input
								v-model="filters.from_date"
								class="edge-input edge-control"
								type="date"
								:disabled="filters.date_preset !== 'custom'"
								@change="applyCustomPeriod"
							/>
						</div>
						<div class="edge-field">
							<label class="edge-field-label">To Date</label>
							<input
								v-model="filters.to_date"
								class="edge-input edge-control"
								type="date"
								:disabled="filters.date_preset !== 'custom'"
								@change="applyCustomPeriod"
							/>
						</div>
					</div>
					<template #actions>
						<button class="edge-button edge-button--primary edge-primary-button" :disabled="loading" @click="refresh">
							Apply / Refresh
						</button>
					</template>
				</EdgeFilterBar>
			</template>

			<div v-if="error" class="vetedge-executive-state">
				<EdgeErrorState title="Dashboard Fetch Failed" :message="error" @retry="refresh" />
			</div>
			<div v-else-if="loading" class="vetedge-executive-state">
				<EdgeLoadingState message="Loading branch performance data..." :skeleton="true" />
			</div>
			<div v-else-if="isEmpty" class="vetedge-executive-state">
				<EdgeEmptyState
					title="No dashboard data"
					description="No performance data was found for the selected branch and date range."
				/>
			</div>
			<div v-else class="vetedge-executive-dashboard-content">
				<section class="vetedge-executive-section">
					<div class="vetedge-executive-section-heading">
						<div><span>Overview</span><h2>Executive Summary</h2></div>
						<small>{{ activePeriodLabel }}</small>
					</div>
					<EdgeDashboardLayout class="vetedge-executive-kpi-grid" minColumnWidth="11rem">
						<EdgeStatCard
							v-for="(card, index) in payload.kpis"
							:key="card.id || card.label || card.title"
							:label="card.label || card.title"
							:value="formatValue(card)"
							:helper="card.secondary_value || ''"
							:tone="cardTone(index)"
							:tooltip="card.tooltip || ''"
						/>
					</EdgeDashboardLayout>
				</section>

				<section v-if="payload.charts?.length" class="vetedge-executive-section">
					<div class="vetedge-executive-section-heading">
						<div><span>Trends</span><h2>Performance Trends</h2></div>
					</div>
					<div class="vetedge-executive-chart-grid">
						<article v-for="(chart, index) in payload.charts" :key="chart.title" class="vetedge-executive-chart-card">
							<header><h3>{{ chart.title }}</h3></header>
							<div :id="`vetedge-executive-chart-${index}`" class="vetedge-executive-chart"></div>
							<div v-if="!chartHasSeries(chart)" class="vetedge-executive-chart-fallback">
								<EdgeEmptyState title="No chart data" description="No values are available for this metric." />
							</div>
						</article>
					</div>
				</section>

				<section v-if="payload.report_links?.length" class="vetedge-executive-section vetedge-executive-reports">
					<div class="vetedge-executive-section-heading">
						<div><span>Explore</span><h2>Quick Reports</h2></div>
					</div>
					<div class="vetedge-executive-report-actions">
						<button
							v-for="link in payload.report_links"
							:key="link.report"
							class="edge-button edge-button--secondary edge-secondary-button"
							@click="openReport(link.report)"
						>{{ link.label }}</button>
					</div>
				</section>
			</div>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
const notificationApi = {
	feed: 'vetedge.services.notification_api.get_my_edgesuite_notifications',
	markRead: 'vetedge.services.notification_api.mark_my_edgesuite_notification_read',
	markAllRead: 'vetedge.services.notification_api.mark_all_my_notifications_read',
	acknowledge: 'vetedge.services.notification_api.acknowledge_my_notification',
	done: 'vetedge.services.notification_api.mark_my_notification_done',
	dismiss: 'vetedge.services.notification_api.dismiss_my_notification'
};

const datePresets = [
	{ value: 'today', label: 'Today' },
	{ value: 'this_week', label: 'This Week' },
	{ value: 'this_month', label: 'This Month' },
	{ value: 'last_30_days', label: 'Last 30 Days' },
	{ value: 'this_quarter', label: 'This Quarter' },
	{ value: 'this_year', label: 'This Year' },
	{ value: 'custom', label: 'Custom Period' }
];

function isoDate(value) {
	const date = new Date(value);
	const offset = date.getTimezoneOffset();
	return new Date(date.getTime() - offset * 60000).toISOString().slice(0, 10);
}

function presetRange(preset) {
	const today = new Date();
	let start = new Date(today);
	let end = new Date(today);

	if (preset === 'this_week') {
		const day = today.getDay() || 7;
		start.setDate(today.getDate() - day + 1);
	} else if (preset === 'this_month') {
		start = new Date(today.getFullYear(), today.getMonth(), 1);
	} else if (preset === 'last_30_days') {
		start.setDate(today.getDate() - 29);
	} else if (preset === 'this_quarter') {
		start = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
	} else if (preset === 'this_year') {
		start = new Date(today.getFullYear(), 0, 1);
	}

	return { from_date: isoDate(start), to_date: isoDate(end) };
}

export default {
	name: 'VetedgeExecutiveDashboard',
	data() {
		const routeOptions = frappe.route_options || {};
		const initialPreset = routeOptions.date_preset || 'this_month';
		const range = routeOptions.from_date && routeOptions.to_date
			? { from_date: routeOptions.from_date, to_date: routeOptions.to_date }
			: presetRange(initialPreset);
		return {
			loading: false,
			error: '',
			branches: [],
			payload: { kpis: [], charts: [], report_links: [] },
			datePresets,
			filters: {
				branch: routeOptions.branch || '',
				date_preset: initialPreset,
				from_date: range.from_date,
				to_date: range.to_date
			},
			tenantName: frappe.boot.sysdefaults?.company || 'Veterinary',
			userName: frappe.boot.user_info?.[frappe.session.user]?.fullname || frappe.session.user,
			menuItems: [
				{ label: 'Executive Dashboard', route: '/app/vetedge-executive-dashboard', icon: '▦' },
				{ label: 'Stock Expiry Monitor', route: '/app/stock-expiry-monitor', icon: '📦' },
				{ label: 'Veterinary Settings', route: '/app/veterinary-settings', icon: '⚙' }
			],
			notificationDrawerOpen: false,
			notificationLoading: false,
			notificationError: '',
			notificationFilter: 'all',
			notificationItems: [],
			notificationUnreadCount: 0,
			chartInstances: []
		};
	},
	computed: {
		isEmpty() {
			return !this.payload.kpis?.length && !this.payload.charts?.length;
		},
		activePeriodLabel() {
			const preset = this.datePresets.find((item) => item.value === this.filters.date_preset);
			return preset?.label || 'Custom Period';
		},
		filteredNotifications() {
			if (this.notificationFilter === 'unread') return this.notificationItems.filter((item) => item.status === 'Unread');
			if (this.notificationFilter === 'action_required') return this.notificationItems.filter((item) => (item.actions || []).length);
			if (this.notificationFilter === 'done') {
				return this.notificationItems.filter((item) => ['Done', 'Dismissed', 'Archived'].includes(item.status));
			}
			return this.notificationItems;
		}
	},
	mounted() {
		window.VetedgeProductMenu?.mount?.();
		this.loadBranches();
		this.fetchNotifications();
		this.refresh();
	},
	beforeUnmount() {
		this.destroyCharts();
	},
	methods: {
		call(method, args = {}) {
			return new Promise((resolve, reject) => {
				frappe.call({
					method,
					args,
					callback: (response) => resolve(response.message || {}),
					error: (response) => reject(response)
				});
			});
		},
		applyPreset() {
			if (this.filters.date_preset !== 'custom') Object.assign(this.filters, presetRange(this.filters.date_preset));
			this.applyFilters();
		},
		applyCustomPeriod() {
			this.filters.date_preset = 'custom';
			this.applyFilters();
		},
		applyFilters() {
			frappe.route_options = { ...this.filters };
			this.refresh();
		},
		async loadBranches() {
			try {
				const rows = await this.call('frappe.client.get_list', {
					doctype: 'Branch',
					fields: ['name'],
					order_by: 'name asc',
					limit_page_length: 500
				});
				this.branches = (rows || []).map((row) => row.name);
			} catch (error) {
				console.warn('Unable to load Executive Dashboard branches', error);
			}
		},
		async refresh() {
			this.loading = true;
			this.error = '';
			frappe.route_options = { ...this.filters };
			try {
				this.payload = await this.call('vetedge.services.reporting_logic_v4.get_dashboard_payload', {
					dashboard_key: 'executive',
					filters: this.filters
				}) || { kpis: [], charts: [], report_links: [] };
				await this.$nextTick();
				this.renderCharts();
			} catch (error) {
				this.error = error?.message || 'Unable to load Executive Dashboard data.';
			} finally {
				this.loading = false;
				await this.$nextTick();
				this.renderCharts();
			}
		},
		formatCurrency(value) {
			const currency = frappe.boot.sysdefaults?.currency || 'NGN';
			try {
				return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(value || 0));
			} catch (_error) {
				return `${currency} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
			}
		},
		formatValue(card) {
			const type = String(card.value_type || card.fieldtype || '').toLowerCase();
			if (type === 'currency') return this.formatCurrency(card.value);
			if (type === 'percent' && typeof card.value === 'number') return `${card.value.toFixed(1)}%`;
			return card.value ?? 0;
		},
		cardTone(index) {
			return ['primary', 'success', 'warning', 'info', 'neutral'][index % 5];
		},
		chartHasSeries(chart) {
			return Boolean(chart.data?.labels?.length && chart.data?.datasets?.some((dataset) => dataset.values?.length));
		},
		destroyCharts() {
			this.chartInstances.forEach((chart) => chart?.destroy?.());
			this.chartInstances = [];
		},
		renderCharts() {
			this.destroyCharts();
			if (!frappe.Chart) return;
			(this.payload.charts || []).forEach((chart, index) => {
				if (!this.chartHasSeries(chart)) return;
				const target = document.getElementById(`vetedge-executive-chart-${index}`);
				if (!target) return;
				try {
					const instance = new frappe.Chart(target, {
						title: '',
						data: chart.data,
						type: chart.type || 'bar',
						colors: chart.colors || ['#1677ff', '#16a34a', '#8b5cf6', '#f59e0b'],
						barOptions: chart.barOptions || { stacked: 0 },
						height: 280,
						tooltipOptions: { formatTooltipY: (value) => this.formatValue({ value, ...chart }) }
					});
					this.chartInstances.push(instance);
				} catch (error) {
					console.warn('Executive Dashboard chart failed to render', error);
					this.renderChartTable(target, chart);
				}
			});
		},
		renderChartTable(target, chart) {
			const labels = chart.data?.labels || [];
			const values = chart.data?.datasets?.[0]?.values || [];
			target.innerHTML = '<div class="table-responsive"><table class="edge-dashboard-table"><tbody>' +
				labels.map((label, index) => `<tr><td>${frappe.utils.escape_html(label)}</td><td class="text-right">${frappe.utils.escape_html(this.formatValue({ value: values[index], ...chart }))}</td></tr>`).join('') +
				'</tbody></table></div>';
		},
		openReport(report) {
			frappe.route_options = { ...this.filters };
			frappe.set_route('query-report', report);
		},
		handleNavigation(route) {
			const parts = String(route || '').replace(/^\/app\//, '').split('/').filter(Boolean);
			if (parts.length) frappe.set_route(parts);
		},
		toggleNotificationDrawer() {
			this.notificationDrawerOpen = !this.notificationDrawerOpen;
			if (this.notificationDrawerOpen) this.fetchNotifications();
		},
		setNotificationFilter(filter) {
			this.notificationFilter = filter;
			this.fetchNotifications();
		},
		async fetchNotifications() {
			this.notificationLoading = true;
			this.notificationError = '';
			try {
				const message = await this.call(notificationApi.feed, { filter_key: this.notificationFilter, limit: 30 });
				this.notificationItems = message.items || [];
				this.notificationUnreadCount = Number(message.unread_count || 0);
			} catch (error) {
				this.notificationError = error?.message || 'Notifications could not be loaded.';
			} finally {
				this.notificationLoading = false;
			}
		},
		async markAllNotificationsRead() {
			await this.call(notificationApi.markAllRead);
			this.fetchNotifications();
		},
		async runNotificationAction(payload) {
			const methods = {
				mark_read: notificationApi.markRead,
				acknowledge: notificationApi.acknowledge,
				done: notificationApi.done,
				dismiss: notificationApi.dismiss
			};
			const method = methods[payload?.action?.key];
			if (!method || !payload?.notification?.name) return;
			await this.call(method, { notification_name: payload.notification.name });
			this.fetchNotifications();
		},
		openNotificationRoute(notification) {
			const parts = String(notification?.route || '').replace(/^\/app\//, '').split('/').filter(Boolean);
			if (parts.length) frappe.set_route(parts.map(decodeURIComponent));
			this.notificationDrawerOpen = false;
		}
	}
};
</script>

<style>
.vetedge-executive-dashboard-root,
.vetedge-executive-dashboard-root .edge-app-shell,
.vetedge-executive-dashboard-root .edge-shell-body,
.vetedge-executive-dashboard-root .edge-shell-main,
.vetedge-executive-dashboard-root .edge-page-layout {
	width: 100%;
	max-width: none;
	min-width: 0;
}
.vetedge-executive-dashboard-root {
	--edge-primary: #1677ff;
	--edge-primary-soft: #e8f2ff;
	--edge-success: #16a34a;
	--edge-warning: #d97706;
	--edge-danger: #dc2626;
	--edge-text: #172033;
	--edge-text-muted: #667085;
	--edge-border: #dbe4f0;
	--edge-bg: #f6f9fc;
	background: linear-gradient(180deg, var(--edge-primary-soft) 0, #f8fbff 180px, var(--edge-bg) 420px);
}
.vetedge-executive-dashboard-root .edge-page-layout__content { padding: 0 28px 32px; }
.vetedge-executive-dashboard-root .edge-page-layout__header,
.vetedge-executive-dashboard-root .edge-page-layout__filters { padding-left: 28px; padding-right: 28px; }
.vetedge-executive-filter-grid {
	display: grid;
	grid-template-columns: repeat(4, minmax(150px, 1fr));
	gap: 14px;
	width: 100%;
}
.vetedge-executive-filter-grid .edge-control {
	width: 100%;
	min-height: 38px;
	padding: 8px 11px;
	border: 1px solid var(--edge-border);
	border-radius: 8px;
	background: #fff;
	color: var(--edge-text);
	box-shadow: 0 1px 2px rgba(15, 23, 42, .04);
}
.vetedge-notification-icon { display: inline-grid; place-items: center; font-size: 1rem; line-height: 1; }
.vetedge-executive-dashboard-content { display: grid; gap: 22px; padding-top: 20px; }
.vetedge-executive-section {
	padding: 20px;
	border: 1px solid var(--edge-border);
	border-radius: 12px;
	background: rgba(255, 255, 255, .96);
	box-shadow: 0 8px 24px rgba(36, 71, 112, .06);
}
.vetedge-executive-section-heading { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.vetedge-executive-section-heading span { color: var(--edge-primary); font-size: .72rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.vetedge-executive-section-heading h2 { margin: 3px 0 0; color: var(--edge-text); font-size: 1.05rem; }
.vetedge-executive-section-heading small { color: var(--edge-text-muted); }
.vetedge-executive-kpi-grid {
	display: grid !important;
	grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)) !important;
	gap: 14px;
}
.vetedge-executive-kpi-grid .edge-stat-card { min-width: 0; border-top: 3px solid var(--edge-primary); }
.vetedge-executive-chart-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
.vetedge-executive-chart-card { min-width: 0; padding: 16px; border: 1px solid var(--edge-border); border-radius: 10px; background: #fff; }
.vetedge-executive-chart-card h3 { margin: 0 0 10px; color: var(--edge-text); font-size: .95rem; }
.vetedge-executive-chart { min-height: 280px; }
.vetedge-executive-report-actions { display: flex; flex-wrap: wrap; gap: 8px; }
.vetedge-executive-state { padding: 28px; }
@media (max-width: 900px) {
	.vetedge-executive-filter-grid { grid-template-columns: repeat(2, minmax(150px, 1fr)); }
	.vetedge-executive-dashboard-root .edge-page-layout__content,
	.vetedge-executive-dashboard-root .edge-page-layout__header,
	.vetedge-executive-dashboard-root .edge-page-layout__filters { padding-left: 18px; padding-right: 18px; }
}
@media (max-width: 576px) {
	.vetedge-executive-filter-grid,
	.vetedge-executive-chart-grid { grid-template-columns: 1fr; }
	.vetedge-executive-section { padding: 14px; }
	.vetedge-executive-dashboard-root .edge-page-layout__content,
	.vetedge-executive-dashboard-root .edge-page-layout__header,
	.vetedge-executive-dashboard-root .edge-page-layout__filters { padding-left: 12px; padding-right: 12px; }
}
</style>
