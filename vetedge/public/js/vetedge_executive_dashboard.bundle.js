import { h } from 'vue';

import VetedgeExecutiveDashboard from './vetedge_executive_dashboard/VetedgeExecutiveDashboard.vue';

const BRANCH_SEARCH_API = 'vetedge.services.dashboard_filter_search.search_dashboard_branches';
const EXECUTIVE_PAYLOAD_API = 'vetedge.services.dashboard_filter_search.get_executive_dashboard_payload';
const BRANCH_SEARCH_PAGE_LENGTH = 20;

function getRuntime() {
	return window.EdgeSuiteUI || window.EdgeUI;
}

function installLowDataBranchPicker(runtime) {
	if (VetedgeExecutiveDashboard.__vetedgeLowDataBranchPickerInstalled) return;
	if (!runtime?.components?.EdgeLinkField) {
		throw new Error('Executive Dashboard requires EdgeSuite UI EdgeLinkField for low-data branch search.');
	}

	const EdgeLinkField = runtime.components.EdgeLinkField;
	const legacyMethods = VetedgeExecutiveDashboard.methods || {};
	const legacyBeforeUnmount = VetedgeExecutiveDashboard.beforeUnmount;

	VetedgeExecutiveDashboard.methods = {
		...legacyMethods,
		async searchDashboardBranches(term = '') {
			const rows = await this.call(BRANCH_SEARCH_API, {
				dashboard_key: 'executive',
				txt: term || '',
				page_length: BRANCH_SEARCH_PAGE_LENGTH,
			});
			return Array.isArray(rows) ? rows : [];
		},
		mountBranchSearch() {
			const dashboardRoot = document.querySelector('.vetedge-executive-dashboard-root');
			const branchField = dashboardRoot?.querySelector('.vetedge-executive-filter-grid .edge-field');
			if (!branchField) return false;

			const nativeLabel = branchField.querySelector('.edge-field-label');
			const nativeSelect = branchField.querySelector('select');
			if (nativeLabel) nativeLabel.style.display = 'none';
			if (nativeSelect) nativeSelect.style.display = 'none';

			if (this._branchSearchView && this._branchSearchHost?.isConnected) {
				this._branchSearchView.value = this.filters.branch || '';
				return true;
			}

			this.unmountBranchSearch?.();
			const dashboard = this;
			const host = document.createElement('div');
			host.className = 'vetedge-executive-branch-search';
			branchField.appendChild(host);

			const pickerApp = runtime.createEdgeApp({
				name: 'VetedgeExecutiveBranchSearch',
				data() {
					return { value: dashboard.filters.branch || '' };
				},
				methods: {
					search(term) {
						return dashboard.searchDashboardBranches(term);
					},
					select(value) {
						this.value = value || '';
						dashboard.filters.branch = this.value;
						dashboard.applyFilters();
					},
				},
				render() {
					return h(EdgeLinkField, {
						modelValue: this.value,
						selectedLabel: this.value || 'All Branches',
						label: 'Branch',
						placeholder: 'Search branches',
						searcher: this.search,
						clearable: true,
						'onUpdate:modelValue': this.select,
					});
				},
			});

			this._branchSearchHost = host;
			this._branchSearchApp = pickerApp;
			this._branchSearchView = pickerApp.mount(host);
			return true;
		},
		unmountBranchSearch() {
			try {
				this._branchSearchApp?.unmount?.();
			} catch (error) {
				console.warn('Unable to unmount Executive Dashboard branch search', error);
			}
			this._branchSearchHost?.remove?.();
			this._branchSearchApp = null;
			this._branchSearchView = null;
			this._branchSearchHost = null;

			const dashboardRoot = document.querySelector('.vetedge-executive-dashboard-root');
			const branchField = dashboardRoot?.querySelector('.vetedge-executive-filter-grid .edge-field');
			const nativeLabel = branchField?.querySelector('.edge-field-label');
			const nativeSelect = branchField?.querySelector('select');
			if (nativeLabel) nativeLabel.style.display = '';
			if (nativeSelect) nativeSelect.style.display = '';
		},
		async refresh() {
			this.loading = true;
			this.error = '';
			frappe.route_options = { ...this.filters };
			try {
				this.payload = await this.call(EXECUTIVE_PAYLOAD_API, {
					filters: this.filters,
				}) || { kpis: [], charts: [], report_links: [] };
				await this.$nextTick();
				this.renderCharts();
			} catch (error) {
				this.error = error?.message || 'Unable to load Executive Dashboard data.';
			} finally {
				this.loading = false;
				await this.$nextTick();
				this.renderCharts();
				this.mountBranchSearch();
			}
		},
	};

	VetedgeExecutiveDashboard.mounted = function mountedLowDataDashboard() {
		window.VetedgeProductMenu?.mount?.();
		this.fetchNotifications();
		this.$nextTick?.(() => this.mountBranchSearch());
		this.refresh();
	};

	VetedgeExecutiveDashboard.beforeUnmount = function beforeUnmountLowDataDashboard() {
		this.unmountBranchSearch?.();
		legacyBeforeUnmount?.call(this);
	};

	VetedgeExecutiveDashboard.__vetedgeLowDataBranchPickerInstalled = true;
}

export function mountVetedgeExecutiveDashboard(target) {
	const runtime = getRuntime();

	if (!runtime?.createEdgeApp || !runtime?.components) {
		throw new Error('Standalone EdgeSuite UI runtime is unavailable.');
	}

	installLowDataBranchPicker(runtime);
	VetedgeExecutiveDashboard.components = runtime.components;
	const app = runtime.createEdgeApp(VetedgeExecutiveDashboard);
	app.mount(target);
	return app;
}

if (typeof window !== 'undefined') {
	const runtime = getRuntime();
	if (runtime?.components) installLowDataBranchPicker(runtime);
	window.VetedgeExecutiveDashboard = VetedgeExecutiveDashboard;
	window.mountVetedgeExecutiveDashboard = mountVetedgeExecutiveDashboard;
}

export { installLowDataBranchPicker };
export default VetedgeExecutiveDashboard;
