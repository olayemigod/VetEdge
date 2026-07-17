<template>
	<EdgeAppShell
		product="vetedge"
		title="Veterinary"
		:menuItems="[]"
		activeRoute="/app/vetedge-executive-dashboard"
		:tenantName="companyName"
		:branchName="filters.branch || 'All Branches'"
		:userName="userName"
		data-edge-product="vetedge"
	>
		<EdgePageLayout>
			<template #header>
				<EdgePageHeader
					title="Executive Dashboard"
					subtitle="Branch-aware operational and financial performance"
					:withBackButton="false"
				/>
			</template>

			<EdgeFilterBar title="Dashboard Filters">
				<div class="edge-filter-grid">
					<div class="edge-field">
						<label class="edge-field-label">Branch</label>
						<select v-model="filters.branch" class="edge-select" @change="refresh">
							<option value="">All Branches</option>
							<option v-for="branch in branches" :key="branch" :value="branch">{{ branch }}</option>
						</select>
					</div>
					<div class="edge-field">
						<label class="edge-field-label">From Date</label>
						<input v-model="filters.from_date" class="edge-input" type="date" @change="refresh" />
					</div>
					<div class="edge-field">
						<label class="edge-field-label">To Date</label>
						<input v-model="filters.to_date" class="edge-input" type="date" @change="refresh" />
					</div>
					<div class="edge-field">
						<label class="edge-field-label" style="visibility: hidden">Action</label>
						<button class="edge-primary-button" :disabled="loading" @click="refresh">Apply / Refresh</button>
					</div>
				</div>
			</EdgeFilterBar>

			<div v-if="error" class="p-6">
				<EdgeErrorState title="Dashboard Fetch Failed" :message="error" @retry="refresh" />
			</div>
			<div v-else-if="loading" class="p-6">
				<EdgeLoadingState message="Loading branch performance data..." :skeleton="true" />
			</div>
			<div v-else-if="isEmpty" class="p-6">
				<EdgeEmptyState
					title="No dashboard data"
					message="No performance data was found for the selected branch and date range."
				/>
			</div>
			<div v-else class="vetedge-executive-dashboard-content">
				<div class="edge-stat-grid">
					<EdgeStatCard
						v-for="card in payload.kpis"
						:key="card.id || card.label || card.title"
						:label="card.label || card.title"
						:value="formatValue(card)"
						:tooltip="card.tooltip || ''"
					/>
				</div>

				<section v-if="payload.charts?.length" class="vetedge-executive-dashboard-charts">
					<article v-for="chart in payload.charts" :key="chart.title" class="edge-table-card">
						<h3>{{ chart.title }}</h3>
						<div v-if="chartRows(chart).length" class="table-responsive">
							<table class="edge-dashboard-table">
								<thead><tr><th>Category</th><th class="text-right">Value</th></tr></thead>
								<tbody>
									<tr v-for="row in chartRows(chart)" :key="row.label">
										<td>{{ row.label }}</td>
										<td class="text-right">{{ formatChartValue(row.value, chart) }}</td>
									</tr>
								</tbody>
							</table>
						</div>
						<EdgeEmptyState v-else title="No chart data" message="No values are available for this metric." />
					</article>
				</section>

				<section v-if="payload.report_links?.length" class="vetedge-executive-dashboard-reports">
					<h3>Quick Reports</h3>
					<div class="d-flex flex-wrap" style="gap: 8px">
						<button
							v-for="link in payload.report_links"
							:key="link.report"
							class="edge-secondary-button"
							@click="openReport(link.report)"
						>{{ link.label }}</button>
					</div>
				</section>
			</div>
		</EdgePageLayout>
	</EdgeAppShell>
</template>

<script>
export default {
	name: 'VetedgeExecutiveDashboard',
	data() {
		const routeOptions = frappe.route_options || {};
		return {
			loading: false,
			error: '',
			branches: [],
			payload: { kpis: [], charts: [], report_links: [] },
			filters: {
				branch: routeOptions.branch || '',
				from_date: routeOptions.from_date || frappe.datetime.month_start(),
				to_date: routeOptions.to_date || frappe.datetime.get_today()
			},
			companyName: frappe.boot.sysdefaults?.company || 'Veterinary',
			userName: frappe.session.user_fullname || frappe.session.user
		};
	},
	computed: {
		isEmpty() {
			return !this.payload.kpis?.length && !this.payload.charts?.length;
		}
	},
	mounted() {
		this.loadBranches();
		this.refresh();
	},
	methods: {
		call(method, args = {}) {
			return new Promise((resolve, reject) => {
				frappe.call({
					method,
					args,
					callback: (response) => resolve(response.message),
					error: (response) => reject(response)
				});
			});
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
			} catch (error) {
				this.error = error?.message || 'Unable to load Executive Dashboard data.';
			} finally {
				this.loading = false;
			}
		},
		formatValue(card) {
			const type = String(card.value_type || card.fieldtype || '').toLowerCase();
			if (type === 'currency' && typeof card.value === 'number') {
				return frappe.format_value(card.value, { fieldtype: 'Currency' });
			}
			if (type === 'percent' && typeof card.value === 'number') return `${card.value.toFixed(1)}%`;
			return card.value ?? 0;
		},
		chartRows(chart) {
			const labels = chart.data?.labels || [];
			const values = chart.data?.datasets?.[0]?.values || [];
			return labels.map((label, index) => ({ label, value: values[index] ?? 0 }));
		},
		formatChartValue(value, chart) {
			return this.formatValue({ value, value_type: chart.value_type, fieldtype: chart.fieldtype });
		},
		openReport(report) {
			frappe.route_options = { ...this.filters };
			frappe.set_route('query-report', report);
		}
	}
};
</script>

<style scoped>
.vetedge-executive-dashboard-content { display: grid; gap: 24px; padding: 20px 0; }
.vetedge-executive-dashboard-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
.vetedge-executive-dashboard-charts article, .vetedge-executive-dashboard-reports { padding: 18px; }
.vetedge-executive-dashboard-charts h3, .vetedge-executive-dashboard-reports h3 { margin: 0 0 14px; font-size: 1rem; }
@media (max-width: 576px) { .vetedge-executive-dashboard-charts { grid-template-columns: 1fr; } }
</style>
