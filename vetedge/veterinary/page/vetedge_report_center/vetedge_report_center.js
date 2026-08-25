const VETEDGE_REPORT_CENTER_STYLE_ID = 'vetedge-report-center-style';

function ensureVetEdgeReportCenterStyles() {
	if (document.getElementById(VETEDGE_REPORT_CENTER_STYLE_ID)) return;
	const style = document.createElement('style');
	style.id = VETEDGE_REPORT_CENTER_STYLE_ID;
	style.textContent = `
		.vetedge-report-center-root,.vetedge-report-center-root .edge-app-shell,.vetedge-report-center-root .edge-shell-body,.vetedge-report-center-root .edge-shell-main,.vetedge-report-center-root .edge-page-layout{width:100%;max-width:none;min-width:0}
		.vetedge-report-center-root .edge-page-layout__content{padding:0 28px 32px}
		.vetedge-report-center-root .edge-page-layout__header,.vetedge-report-center-root .edge-page-layout__filters{padding-left:28px;padding-right:28px}
		.vetedge-report-center-filter-grid{display:grid;grid-template-columns:repeat(3,minmax(12rem,1fr));gap:14px;width:100%;align-items:end}
		.vetedge-report-center-filter-grid--service{grid-template-columns:repeat(3,minmax(11rem,1fr))}
		.vetedge-report-center-content{display:grid;gap:22px;padding-top:20px}
		.vetedge-report-center-section{padding:20px;border:1px solid var(--edge-color-border);border-radius:12px;background:var(--edge-color-surface);box-shadow:var(--edge-shadow-sm,0 8px 24px rgb(18 32 51 / 6%));min-width:0}
		.vetedge-report-center-heading{display:flex;align-items:end;justify-content:space-between;gap:12px;margin-bottom:16px}
		.vetedge-report-center-heading span{color:var(--edge-color-brand-600);font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
		.vetedge-report-center-heading h2{margin:3px 0 0;color:var(--edge-color-ink-950);font-size:1.05rem}
		.vetedge-report-center-heading p{margin:.3rem 0 0;color:var(--edge-color-ink-500)}
		.vetedge-report-center-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(12rem,1fr));gap:14px}
		.vetedge-report-center-summary .edge-stat-card{border-top:3px solid var(--edge-color-brand-600)}
		.vetedge-report-center-chart{min-height:280px}
		.vetedge-report-center-actions{display:flex;gap:8px;flex-wrap:wrap}
		:root[data-edge-palette] .vetedge-report-center-root .edge-shell-main{background:linear-gradient(180deg,var(--edge-color-brand-50) 0,var(--edge-color-surface-soft) 180px,var(--edge-color-surface-muted) 420px)!important}
		:root[data-edge-palette] .graph-svg-tip,:root[data-edge-appearance] .graph-svg-tip{background:var(--edge-color-surface)!important;border:1px solid var(--edge-color-border)!important;color:var(--edge-color-ink-950)!important}
		:root[data-edge-palette] .graph-svg-tip *,:root[data-edge-appearance] .graph-svg-tip *{color:var(--edge-color-ink-950)!important;fill:var(--edge-color-ink-950)!important;opacity:1!important}
		@media(max-width:900px){.vetedge-report-center-filter-grid,.vetedge-report-center-filter-grid--service{grid-template-columns:repeat(2,minmax(10rem,1fr))}.vetedge-report-center-root .edge-page-layout__content,.vetedge-report-center-root .edge-page-layout__header,.vetedge-report-center-root .edge-page-layout__filters{padding-left:18px;padding-right:18px}}
		@media(max-width:576px){.vetedge-report-center-filter-grid,.vetedge-report-center-filter-grid--service{grid-template-columns:1fr}.vetedge-report-center-root .edge-page-layout__content,.vetedge-report-center-root .edge-page-layout__header,.vetedge-report-center-root .edge-page-layout__filters{padding-left:12px;padding-right:12px}.vetedge-report-center-actions,.vetedge-report-center-actions .edge-button{width:100%}}
	`;
	document.head.appendChild(style);
}

function vetedgeReportCall(method, args = {}) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method,
			args,
			callback: (response) => resolve(response.message || {}),
			error: reject,
		});
	});
}

function reportCenterProfile() {
	const boot = frappe.boot || {};
	const user = frappe.session?.user || '';
	const info = boot.user_info?.[user] || {};
	return {
		tenantName: boot.sysdefaults?.company || '',
		branchName: frappe.route_options?.branch || frappe.defaults?.get_user_default?.('branch') || 'All Branches',
		userName: info.fullname || info.full_name || user,
	};
}

function reportCenterRoute(route) {
	const target = String(route || '').trim();
	if (!target) return false;
	if (window.VetEdgeNavigationRecovery?.navigate?.(target) === true) return true;
	if (window.VetEdgeProfessionalUI?.openRoute?.(target) === true) return true;
	try {
		const url = new URL(target, window.location.origin);
		if (url.origin === window.location.origin && /^\/desk(?:\/|$)/.test(url.pathname) && typeof frappe.set_route === 'function') {
			frappe.route_options = {};
			for (const [key, value] of url.searchParams) frappe.route_options[key] = value;
			const parts = url.pathname.replace(/^\/desk(?:\/|$)/, '').split('/').filter(Boolean).map(decodeURIComponent);
			if (parts.length) {
				frappe.set_route(...parts);
				return true;
			}
		}
	} catch (_error) {
		// Fall through to normal browser navigation.
	}
	window.location.assign(target);
	return true;
}

function reportCenterParams() {
	const params = new URLSearchParams(window.location.search || '');
	const routeOptions = frappe.route_options || {};
	const get = (key, fallback = '') => params.get(key) || routeOptions[key] || fallback;
	return {
		report: get('report'),
		source: get('source', '/desk/vetedge-executive-dashboard'),
		branch: get('branch'),
		from_date: get('from_date'),
		to_date: get('to_date'),
		date_preset: get('date_preset'),
		customer: get('customer'),
		practitioner: get('practitioner'),
		service_category: get('service_category'),
		item: get('item'),
	};
}

function parseReportColumn(column, index) {
	if (typeof column === 'string') {
		const [label, fieldname, fieldtype, width] = column.split(':');
		return {
			label: label || `Column ${index + 1}`,
			fieldname: fieldname || `column_${index + 1}`,
			fieldtype: fieldtype || 'Data',
			width: Number(width || 0) || undefined,
		};
	}
	return {
		...column,
		label: column?.label || column?.fieldname || `Column ${index + 1}`,
		fieldname: column?.fieldname || column?.key || `column_${index + 1}`,
		fieldtype: column?.fieldtype || column?.type || 'Data',
	};
}

frappe.pages['vetedge-report-center'].on_page_load = function(wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __('Veterinary Quick Report'), single_column: true });
	wrapper.page = page;
};

frappe.pages['vetedge-report-center'].on_page_show = function(wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	ensureVetEdgeReportCenterStyles();

	const $loading = $('<div class="p-6 text-center text-muted"></div>').text(__('Loading EdgeSuite report...')).appendTo(page.body);
	const showFailure = (message) => {
		$loading.remove();
		$('<div class="alert alert-danger p-6 text-center"></div>').text(message || __('Quick report failed to load.')).appendTo(page.body);
	};

	frappe.require('edgeui.bundle.js', () => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ['EdgeAppShell','EdgePageLayout','EdgePageHeader','EdgeFilterBar','EdgeLinkField','EdgeDropdown','EdgeInput','EdgeDataTable','EdgeDashboardLayout','EdgeStatCard','EdgeLoadingState','EdgeErrorState','EdgeEmptyState'];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || !runtime?.Vue?.h || missing.length) {
			showFailure(missing.length ? __('Quick Reports require EdgeSuite UI 0.6.3 or newer. Missing: {0}', [missing.join(', ')]) : __('The EdgeSuite UI runtime is unavailable.'));
			return;
		}

		const mountReport = () => {
			if (wrapper.current_visit_id !== visitId) return;
			const professional = window.VetEdgeProfessionalUI?.install?.();
			window.VetEdgeUIBridge?.install?.();
			window.VetEdgeNavigationRecovery?.install?.();
			if (!professional?.installed) {
				showFailure(professional?.message || __('The VetEdge professional shell is unavailable.'));
				return;
			}

			const h = runtime.Vue.h;
			const nextTick = runtime.Vue.nextTick;
			const { EdgeAppShell, EdgePageLayout, EdgePageHeader, EdgeFilterBar, EdgeLinkField, EdgeDropdown, EdgeInput, EdgeDataTable, EdgeDashboardLayout, EdgeStatCard, EdgeLoadingState, EdgeErrorState, EdgeEmptyState } = runtime.components;
			const initial = reportCenterParams();
			const profile = reportCenterProfile();
			const serviceCategories = ['', 'Consultation Service', 'Treatment', 'Registration', 'Vaccination', 'Lab', 'Grooming', 'Boarding', 'Hospitalisation', 'Dispensary / Pharmacy', 'General / Other'].map((value) => ({ value, label: value || __('All Service Categories') }));

			const component = {
				name: 'VetEdgeReportCenter',
				data() {
					return {
						reportName: initial.report,
						sourceRoute: initial.source,
						filters: {
							branch: initial.branch || '',
							from_date: initial.from_date || '',
							to_date: initial.to_date || '',
							date_preset: initial.date_preset || '',
							customer: initial.customer || '',
							practitioner: initial.practitioner || '',
							service_category: initial.service_category || '',
							item: initial.item || '',
						},
						loading: false,
						error: '',
						columns: [],
						rows: [],
						reportSummary: [],
						chart: null,
						chartInstance: null,
					};
				},
				mounted() { this.refresh(); },
				beforeUnmount() { this.chartInstance?.destroy?.(); },
				methods: {
					isServiceRevenue() { return this.reportName === 'Service Revenue Breakdown'; },
					async searchLink(doctype, term) {
						const response = await frappe.call('frappe.desk.search.search_link', { doctype, txt: term || '', page_length: 20, ignore_user_permissions: 0 });
						return response.message || [];
					},
					searchBranches(term) { return this.searchLink('Branch', term); },
					searchItems(term) { return this.searchLink('Item', term); },
					reportFilters() {
						const result = {};
						for (const fieldname of ['branch','from_date','to_date','customer','practitioner','service_category','item']) {
							const value = this.filters[fieldname];
							if (value !== undefined && value !== null && String(value) !== '') result[fieldname] = value;
						}
						return result;
					},
					updateLocation() {
						const params = new URLSearchParams({ report: this.reportName, source: this.sourceRoute || '/desk/vetedge-executive-dashboard' });
						for (const [key, value] of Object.entries(this.filters)) if (value) params.set(key, value);
						window.history.replaceState({}, '', `/desk/vetedge-report-center?${params.toString()}`);
					},
					formatValue(value, fieldtype = 'Data') {
						if (value === undefined || value === null || value === '') return '—';
						if (fieldtype === 'Currency') {
							const currency = frappe.boot?.sysdefaults?.currency || 'NGN';
							try { return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(value || 0)); }
							catch (_error) { return `${currency} ${Number(value || 0).toLocaleString()}`; }
						}
						if (fieldtype === 'Int') return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
						if (fieldtype === 'Float' || fieldtype === 'Percent') return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
						if (fieldtype === 'Date' || fieldtype === 'Datetime') return frappe.datetime?.str_to_user?.(value) || value;
						return String(value);
					},
					normalizeResult(payload) {
						this.columns = (payload.columns || []).map(parseReportColumn);
						const sourceRows = payload.result || payload.rows || [];
						this.rows = sourceRows.map((row, rowIndex) => {
							const source = Array.isArray(row)
								? Object.fromEntries(this.columns.map((column, index) => [column.fieldname, row[index]]))
								: row;
							const normalized = { __row_key: source?.name || source?.invoice || `row-${rowIndex}` };
							for (const column of this.columns) normalized[column.fieldname] = this.formatValue(source?.[column.fieldname], column.fieldtype);
							return normalized;
						});
						this.reportSummary = payload.report_summary || [];
						this.chart = payload.chart || null;
					},
					async refresh() {
						if (!this.reportName) { this.error = __('No report was selected.'); return; }
						this.loading = true;
						this.error = '';
						this.chartInstance?.destroy?.();
						this.chartInstance = null;
						try {
							const payload = await vetedgeReportCall('frappe.desk.query_report.run', {
								report_name: this.reportName,
								filters: JSON.stringify(this.reportFilters()),
								ignore_prepared_report: 1,
								are_default_filters: false,
							});
							this.normalizeResult(payload || {});
							this.updateLocation();
							await nextTick();
							this.renderChart();
						} catch (error) {
							this.error = error?.message || error?._server_messages || __('The report could not be generated.');
						} finally {
							this.loading = false;
							await nextTick();
							this.renderChart();
						}
					},
					renderChart() {
						if (!this.chart?.data || !frappe.Chart || !this.$el) return;
						const target = this.$el.querySelector('[data-vetedge-report-chart]');
						if (!target) return;
						this.chartInstance?.destroy?.();
						try {
							this.chartInstance = new frappe.Chart(target, { ...this.chart, height: 280, colors: ['var(--edge-color-brand-600)', '#16a34a', '#7c3aed', '#d97706', '#0891b2', '#dc2626'] });
						} catch (error) { console.warn('VetEdge quick report chart failed to render', error); }
					},
					back() { reportCenterRoute(this.sourceRoute || '/desk/vetedge-executive-dashboard'); },
					renderFilters() {
						const common = [
							h(EdgeLinkField, { modelValue: this.filters.branch, selectedLabel: this.filters.branch || __('All Branches'), label: __('Branch'), placeholder: __('All Branches'), searcher: this.searchBranches, allowClear: true, 'onUpdate:modelValue': (value) => { this.filters.branch = value || ''; } }),
							h(EdgeInput, { modelValue: this.filters.from_date, label: __('From Date'), type: 'date', 'onUpdate:modelValue': (value) => { this.filters.from_date = value || ''; } }),
							h(EdgeInput, { modelValue: this.filters.to_date, label: __('To Date'), type: 'date', 'onUpdate:modelValue': (value) => { this.filters.to_date = value || ''; } }),
						];
						if (!this.isServiceRevenue()) return h('div', { class: 'vetedge-report-center-filter-grid' }, common);
						return h('div', { class: 'vetedge-report-center-filter-grid vetedge-report-center-filter-grid--service' }, [
							...common,
							h(EdgeDropdown, { modelValue: this.filters.service_category, label: __('Service Category'), options: serviceCategories, 'onUpdate:modelValue': (value) => { this.filters.service_category = value || ''; } }),
							h(EdgeInput, { modelValue: this.filters.practitioner, label: __('Practitioner'), placeholder: __('All Practitioners'), 'onUpdate:modelValue': (value) => { this.filters.practitioner = value || ''; } }),
							h(EdgeLinkField, { modelValue: this.filters.item, selectedLabel: this.filters.item, label: __('Item'), placeholder: __('All Items'), searcher: this.searchItems, allowClear: true, 'onUpdate:modelValue': (value) => { this.filters.item = value || ''; } }),
						]);
					},
					renderSummary() {
						if (!this.reportSummary?.length) return null;
						return h(EdgeDashboardLayout, { minColumnWidth: '12rem', class: 'vetedge-report-center-summary' }, {
							default: () => this.reportSummary.map((card, index) => h(EdgeStatCard, {
								label: card.label || __('Metric'),
								value: this.formatValue(card.value, ['Revenue','Paid','Outstanding'].includes(card.label) ? 'Currency' : 'Data'),
								tone: ['primary','success','warning','info'][index % 4],
							})),
						});
					},
				},
				render() {
					return h(EdgeAppShell, {
						product: 'vetedge', title: 'Veterinary', tenantName: profile.tenantName,
						branchName: this.filters.branch || profile.branchName,
						userName: profile.userName,
						activeRoute: this.sourceRoute || '/desk/vetedge-executive-dashboard',
					}, {
						default: () => h(EdgePageLayout, {}, {
							header: () => h(EdgePageHeader, { eyebrow: __('Quick Report'), title: this.reportName || __('Veterinary Report'), subtitle: __('EdgeSuite report view using the dashboard scope that opened this report.') }, {
								actions: () => h('button', { class: 'edge-button edge-button--secondary', type: 'button', onClick: this.back }, __('Back to Dashboard')),
							}),
							filters: () => h(EdgeFilterBar, { title: __('Report Filters') }, {
								default: () => this.renderFilters(),
								actions: () => h('div', { class: 'vetedge-report-center-actions' }, [h('button', { class: 'edge-button edge-button--primary', type: 'button', disabled: this.loading, onClick: this.refresh }, this.loading ? __('Refreshing…') : __('Apply / Refresh'))]),
							}),
							default: () => this.error
								? h('div', { class: 'vetedge-report-center-content' }, [h(EdgeErrorState, { title: __('Report Failed'), message: this.error, onRetry: this.refresh })])
								: this.loading
									? h('div', { class: 'vetedge-report-center-content' }, [h(EdgeLoadingState, { message: __('Generating report…'), skeleton: true })])
									: h('div', { class: 'vetedge-report-center-content' }, [
										this.renderSummary(),
										this.chart?.data ? h('section', { class: 'vetedge-report-center-section' }, [h('div', { class: 'vetedge-report-center-heading' }, [h('div', [h('span', __('Chart')), h('h2', this.chart.title || this.reportName)])]), h('div', { class: 'vetedge-report-center-chart', 'data-vetedge-report-chart': '1' })]) : null,
										h('section', { class: 'vetedge-report-center-section' }, [h('div', { class: 'vetedge-report-center-heading' }, [h('div', [h('span', __('Detail')), h('h2', this.reportName || __('Report Results')), h('p', __('Filters are retained in the URL and can be refreshed without leaving EdgeSuite UI.'))])]), this.rows.length ? h(EdgeDataTable, { columns: this.columns, rows: this.rows, rowKey: '__row_key' }) : h(EdgeEmptyState, { title: __('No report rows'), description: __('No records match the selected report filters.') })]),
									].filter(Boolean)),
						}),
					});
				},
			};

			try {
				$loading.remove();
				const root = $('<div class="vetedge-report-center-root" data-edge-product="vetedge"></div>').appendTo(page.body);
				wrapper.vue_app = runtime.createEdgeApp(component);
				wrapper.vue_app.mount(root[0]);
			} catch (error) {
				console.error('Error mounting VetEdge Quick Report Center:', error);
				showFailure(__('Error mounting Quick Report Center: {0}', [error.message || String(error)]));
			}
		};

		if (window.VetEdgeProfessionalUI?.install) mountReport();
		else frappe.require('/assets/vetedge/js/vetedge_professional_ui.js', mountReport);
	});
};
