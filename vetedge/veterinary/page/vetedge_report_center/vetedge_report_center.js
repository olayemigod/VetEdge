const VETEDGE_REPORT_CENTER_STYLE_ID = "vetedge-report-center-style";
const VETEDGE_REPORT_PAGE_LENGTH = 50;
const CAPABILITIES_API = "vetedge.services.reporting_capabilities.get_shell_capabilities";
const SMART_FILTER_API = "vetedge.services.report_filter_search.search_report_filter_options";
const SAVED_VIEWS_GET_API = "vetedge.services.report_saved_views.get_saved_report_views";
const SAVED_VIEWS_APPLY_API = "vetedge.services.report_saved_views.apply_saved_report_view";
const SAVED_VIEWS_SAVE_API = "vetedge.services.report_saved_views.save_report_view";
const SAVED_VIEWS_RENAME_API = "vetedge.services.report_saved_views.rename_saved_report_view";
const SAVED_VIEWS_DELETE_API = "vetedge.services.report_saved_views.delete_saved_report_view";
const REPORT_COMPARISON_API = "vetedge.services.report_comparison.get_report_comparison";
const REPORT_FILTER_KEYS = [
	"branch", "from_date", "to_date", "date_preset", "customer", "patient", "practitioner",
	"consultation_type", "status", "payment_status", "service_category", "item", "vaccine",
	"due_status", "species", "breed", "registration_status", "outstanding_only",
];

function ensureVetEdgeReportCenterStyles() {
	if (document.getElementById(VETEDGE_REPORT_CENTER_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = VETEDGE_REPORT_CENTER_STYLE_ID;
	style.textContent = `
		.vetedge-report-center-root,.vetedge-report-center-root .edge-app-shell,.vetedge-report-center-root .edge-shell-body,.vetedge-report-center-root .edge-shell-main,.vetedge-report-center-root .edge-page-layout{width:100%;max-width:none;min-width:0}
		.vetedge-report-center-filter-grid{display:grid;grid-template-columns:repeat(3,minmax(12rem,1fr));gap:14px;width:100%;align-items:end}
		.vetedge-report-center-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
		.vetedge-report-center-saved-view{min-width:12rem;max-width:18rem}
		.vetedge-report-provider-badge{display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;background:var(--edge-color-surface-muted);color:var(--edge-color-ink-500);font-size:.7rem;font-weight:600}
		.vetedge-report-center-chart{min-height:280px}
		.vetedge-report-center-insights{display:grid;gap:1rem}
		:root[data-edge-palette] .vetedge-report-center-root .edge-shell-main{background:linear-gradient(180deg,var(--edge-color-brand-50) 0,var(--edge-color-surface-soft) 180px,var(--edge-color-surface-muted) 420px)!important}
		:root[data-edge-palette] .graph-svg-tip,:root[data-edge-appearance] .graph-svg-tip{background:var(--edge-color-surface)!important;border:1px solid var(--edge-color-border)!important;color:var(--edge-color-ink-950)!important}
		@media(max-width:900px){.vetedge-report-center-filter-grid{grid-template-columns:repeat(2,minmax(10rem,1fr))}}
		@media(max-width:576px){.vetedge-report-center-filter-grid{grid-template-columns:1fr}.vetedge-report-center-actions,.vetedge-report-center-actions .edge-button,.vetedge-report-center-saved-view{width:100%;max-width:none}}
	`;
	document.head.appendChild(style);
}

function reportCenterProfile() {
	const boot = frappe.boot || {};
	const user = frappe.session?.user || "";
	const info = boot.user_info?.[user] || {};
	return {
		tenantName: boot.sysdefaults?.company || "",
		branchName: frappe.route_options?.branch || frappe.defaults?.get_user_default?.("branch") || "All Branches",
		userName: info.fullname || info.full_name || user,
	};
}

function reportCenterRoute(route) {
	const target = String(route || "").trim();
	if (!target) return false;
	if (window.VetEdgeNavigationRecovery?.navigate?.(target) === true) return true;
	if (window.VetEdgeProfessionalUI?.openRoute?.(target) === true) return true;
	try {
		const url = new URL(target, window.location.origin);
		if (url.origin === window.location.origin && /^\/desk(?:\/|$)/.test(url.pathname) && typeof frappe.set_route === "function") {
			frappe.route_options = {};
			for (const [key, value] of url.searchParams) frappe.route_options[key] = value;
			const parts = url.pathname.replace(/^\/desk(?:\/|$)/, "").split("/").filter(Boolean).map(decodeURIComponent);
			if (parts.length) {
				frappe.set_route(...parts);
				return true;
			}
		}
	} catch (_error) {
		// Fall back to normal browser navigation.
	}
	window.location.assign(target);
	return true;
}

function normalizeReportColumnKeys(value) {
	const values = Array.isArray(value) ? value : String(value || "").split(",");
	return [...new Set(values.map((item) => String(item || "").trim()).filter(Boolean))];
}

function reportCenterParams() {
	const params = new URLSearchParams(window.location.search || "");
	const routeOptions = frappe.route_options || {};
	const get = (key, fallback = "") => params.get(key) || routeOptions[key] || fallback;
	const result = {
		report: get("report"),
		source: get("source", "/desk/vetedge-executive-dashboard"),
		columns: get("columns"),
	};
	for (const key of REPORT_FILTER_KEYS) result[key] = get(key);
	return result;
}

function loadProviderAssets(callback) {
	frappe.require("/assets/vetedge/js/vetedge_report_provider_adapter.js", () => {
		frappe.require("/assets/vetedge/js/vetedge_report_provider_registry.js", () => {
			frappe.require("/assets/vetedge/js/vetedge_report_filter_ui.js", () => {
				window.VetEdgeReportProviderRegistry?.register?.();
				callback();
			});
		});
	});
}

frappe.pages["vetedge-report-center"].on_page_load = function (wrapper) {
	wrapper.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Veterinary Quick Report"), single_column: true });
};

frappe.pages["vetedge-report-center"].on_page_show = function (wrapper) {
	const page = wrapper.page;
	wrapper.current_visit_id = (wrapper.current_visit_id || 0) + 1;
	const visitId = wrapper.current_visit_id;
	wrapper.vue_app?.unmount?.();
	wrapper.vue_app = null;
	$(page.body).empty();
	ensureVetEdgeReportCenterStyles();
	const $loading = $("<div class='p-6 text-center text-muted'></div>").text(__("Loading EdgeSuite report...")).appendTo(page.body);
	const fail = (message) => {
		$loading.remove();
		$("<div class='alert alert-danger p-6 text-center'></div>").text(message || __("Quick report failed to load.")).appendTo(page.body);
	};

	frappe.require("edgeui.bundle.js", () => loadProviderAssets(() => {
		if (wrapper.current_visit_id !== visitId) return;
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		const required = ["EdgeAppShell", "EdgeReportShell", "EdgeLinkField", "EdgeDropdown", "EdgeInput"];
		const missing = required.filter((name) => !runtime?.components?.[name]);
		if (!runtime?.createEdgeApp || !runtime?.Vue?.h || missing.length || !window.VetEdgeReportFilterUI) {
			fail(__("Quick Reports require the current EdgeSuite UI and VetEdge report-filter runtime. Missing: {0}", [missing.join(", ")]));
			return;
		}

		window.VetEdgeProfessionalUI?.install?.();
		window.VetEdgeUIBridge?.install?.();
		window.VetEdgeNavigationRecovery?.install?.();
		const h = runtime.Vue.h;
		const nextTick = runtime.Vue.nextTick;
		const { EdgeAppShell, EdgeReportShell, EdgeLinkField, EdgeDropdown, EdgeInput } = runtime.components;
		const EdgeReportComparisonPanel = runtime.components.EdgeReportComparisonPanel || null;
		const initial = reportCenterParams();
		const profile = reportCenterProfile();

		const component = {
			name: "VetEdgeReportCenter",
			data() {
				const filters = {};
				for (const key of REPORT_FILTER_KEYS) filters[key] = initial[key] || "";
				return {
					reportName: initial.report,
					sourceRoute: initial.source,
					filters,
					viewState: { visible_columns: normalizeReportColumnKeys(initial.columns) },
					savedViews: [],
					selectedSavedViewId: "",
					savedViewsLoading: false,
					loading: false,
					error: "",
					provider: null,
					pageStart: 0,
					pageLength: VETEDGE_REPORT_PAGE_LENGTH,
					result: { columns: [], rows: [], summary: [], chart: null, total: 0, start: 0, page_length: VETEDGE_REPORT_PAGE_LENGTH, has_previous: false, has_next: false, metadata: {} },
					chartInstance: null,
					exportBusy: false,
					printBusy: false,
					comparisonLoading: false,
					comparison: null,
					capabilities: { can_view: true, can_print: false, can_export: false, report_tier: "", subscription_entitled: true, advanced_features_entitled: false },
				};
			},
			async mounted() {
				await this.refresh();
				if (this.capabilities.can_view !== false) await this.loadSavedViews();
			},
			beforeUnmount() { this.chartInstance?.destroy?.(); },
			computed: {
				providerLabel() {
					if (!this.provider) return __("Query Report");
					if (["query-level", "query-level-detail"].includes(this.result.metadata?.pagination_mode)) return __("Optimized paginated provider");
					if (this.result.metadata?.pagination_mode === "materialize-then-slice") return __("Paged response · optimization pending");
					return this.provider.kind === "paginated" ? __("Paginated provider") : __("Query Report provider");
				},
				savedViewOptions() {
					return (this.savedViews || []).map((view) => ({ value: view.view_id, label: view.label }));
				},
				selectedSavedView() {
					return (this.savedViews || []).find((view) => view.view_id === this.selectedSavedViewId) || null;
				},
				comparisonSupported() {
					return Boolean(EdgeReportComparisonPanel && this.reportName === "Consultation Register");
				},
				pagination() {
					const pageSize = Number(this.result.page_length || this.pageLength || VETEDGE_REPORT_PAGE_LENGTH);
					const total = Number(this.result.total || 0);
					const start = Number(this.result.start || this.pageStart || 0);
					return {
						page: Math.floor(start / Math.max(1, pageSize)) + 1,
						page_size: pageSize,
						total_rows: total,
						total_pages: Math.max(1, Math.ceil(total / Math.max(1, pageSize))),
						has_previous: Boolean(this.result.has_previous),
						has_next: Boolean(this.result.has_next),
					};
				},
			},
			methods: {
				filterSearchReportName() {
					return this.reportName === "Laboratory Report" ? "Lab Order Report" : this.reportName;
				},
				async searchGenericLink(doctype, term) {
					const response = await frappe.call("frappe.desk.search.search_link", { doctype, txt: term || "", page_length: 20, ignore_user_permissions: 0 });
					return response.message || [];
				},
				async searchReportFilter(reportName, field, term) {
					const response = await frappe.call(SMART_FILTER_API, {
						report_name: reportName || this.filterSearchReportName(),
						field,
						txt: term || "",
						start: 0,
						page_length: 20,
						filters: JSON.stringify(this.reportFilters()),
					});
					return response.message || [];
				},
				setFilter(field, value) {
					const previous = this.filters[field] || "";
					if (previous === value) return;
					if (field === "branch") {
						this.filters.patient = "";
						this.filters.customer = "";
						this.filters.practitioner = "";
					}
					if (field === "customer") this.filters.patient = "";
					if (field === "patient") this.filters.customer = "";
					if (field === "species") this.filters.breed = "";
					this.filters[field] = value || "";
					this.selectedSavedViewId = "";
					this.comparison = null;
				},
				reportFilters() {
					return Object.fromEntries(Object.entries(this.filters).filter(([, value]) => value !== undefined && value !== null && String(value) !== ""));
				},
				async loadCapabilities() {
					if (!this.reportName) return;
					try {
						if (window.VetEdgeReportingCapabilities?.get) {
							this.capabilities = await window.VetEdgeReportingCapabilities.get(this.reportName, "report", { refresh: true });
						} else {
							const response = await frappe.call(CAPABILITIES_API, { scope_name: this.reportName, scope_type: "report" });
							this.capabilities = response.message || this.capabilities;
						}
					} catch (error) {
						console.warn("VetEdge Report Center capabilities could not be loaded", error);
						this.capabilities = { can_view: true, can_print: false, can_export: false, report_tier: "", subscription_entitled: true, advanced_features_entitled: false };
					}
				},
				async loadSavedViews() {
					if (!this.reportName || this.capabilities.can_view === false) return;
					this.savedViewsLoading = true;
					try {
						const response = await frappe.call(SAVED_VIEWS_GET_API, { report_name: this.reportName });
						this.savedViews = Array.isArray(response.message) ? response.message : [];
						if (this.selectedSavedViewId && !this.savedViews.some((view) => view.view_id === this.selectedSavedViewId)) this.selectedSavedViewId = "";
					} catch (error) {
						console.warn("VetEdge saved report views could not be loaded", error);
						this.savedViews = [];
					} finally {
						this.savedViewsLoading = false;
					}
				},
				resolveProvider() {
					const adapters = window.VetEdgeReportProviders;
					this.provider = adapters?.getProvider?.(this.reportName) || adapters?.ensureQueryProvider?.(this.reportName, this.reportName) || null;
					return this.provider;
				},
				updateLocation() {
					const params = new URLSearchParams({ report: this.reportName, source: this.sourceRoute || "/desk/vetedge-executive-dashboard" });
					for (const [key, value] of Object.entries(this.filters)) if (value) params.set(key, value);
					const visibleColumns = normalizeReportColumnKeys(this.viewState?.visible_columns);
					if (visibleColumns.length) params.set("columns", visibleColumns.join(","));
					window.history.replaceState({}, "", `/desk/vetedge-report-center?${params.toString()}`);
				},
				setViewState(state = {}) {
					this.viewState = { visible_columns: normalizeReportColumnKeys(state.visible_columns) };
					this.selectedSavedViewId = "";
					this.updateLocation();
				},
				async applySavedView(viewId) {
					if (!viewId) { this.selectedSavedViewId = ""; return; }
					try {
						const response = await frappe.call(SAVED_VIEWS_APPLY_API, { view_id: viewId, report_name: this.reportName });
						const state = response.message || {};
						const nextFilters = {};
						for (const key of REPORT_FILTER_KEYS) nextFilters[key] = state.filters?.[key] ?? "";
						this.filters = nextFilters;
						this.viewState = { visible_columns: normalizeReportColumnKeys(state.visible_columns) };
						this.selectedSavedViewId = state.view?.view_id || viewId;
						this.pageStart = 0;
						this.comparison = null;
						this.updateLocation();
						if (Array.isArray(state.removed_filter_keys) && state.removed_filter_keys.length) {
							frappe.show_alert?.({ message: __("Some saved filters were removed because your current access or report context changed."), indicator: "orange" });
						}
						await this.refresh(true);
					} catch (error) {
						this.selectedSavedViewId = "";
						frappe.msgprint({ title: __("Saved View Failed"), message: error?.message || __("The saved view could not be applied."), indicator: "red" });
					}
				},
				promptSaveView(existing = null) {
					frappe.prompt(
						[{ fieldname: "label", fieldtype: "Data", label: __("View Name"), reqd: 1, default: existing?.label || "" }],
						async (values) => {
							try {
								let response;
								if (existing) {
									response = await frappe.call(SAVED_VIEWS_RENAME_API, { view_id: existing.view_id, report_name: this.reportName, label: values.label });
								} else {
									response = await frappe.call(SAVED_VIEWS_SAVE_API, {
										label: values.label,
										report_name: this.reportName,
										filters: JSON.stringify(this.reportFilters()),
										visible_columns: JSON.stringify(normalizeReportColumnKeys(this.viewState?.visible_columns)),
										set_default: 0,
									});
								}
								await this.loadSavedViews();
								this.selectedSavedViewId = response.message?.view_id || existing?.view_id || "";
								frappe.show_alert?.({ message: existing ? __("Saved view renamed.") : __("Saved view created."), indicator: "green" });
							} catch (error) {
								frappe.msgprint({ title: __("Saved View Failed"), message: error?.message || __("The saved view could not be stored."), indicator: "red" });
							}
						},
						__(existing ? "Rename Saved View" : "Save Current View"),
						__(existing ? "Rename" : "Save"),
					);
				},
				deleteSelectedSavedView() {
					const view = this.selectedSavedView;
					if (!view) return;
					frappe.confirm(
						__("Delete saved view {0}?", [view.label]),
						async () => {
							try {
								await frappe.call(SAVED_VIEWS_DELETE_API, { view_id: view.view_id });
								this.selectedSavedViewId = "";
								await this.loadSavedViews();
								frappe.show_alert?.({ message: __("Saved view deleted."), indicator: "green" });
							} catch (error) {
								frappe.msgprint({ title: __("Delete Saved View Failed"), message: error?.message || __("The saved view could not be deleted."), indicator: "red" });
							}
						},
					);
				},
				formatValue(value, column = {}) {
					if (value === undefined || value === null || value === "") return "—";
					const fieldtype = column.fieldtype || column.datatype || "Data";
					if (fieldtype === "Currency") {
						const currency = frappe.boot?.sysdefaults?.currency || "NGN";
						try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value || 0)); }
						catch (_error) { return `${currency} ${Number(value || 0).toLocaleString()}`; }
					}
					if (["Int", "Float", "Percent"].includes(fieldtype)) return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: fieldtype === "Int" ? 0 : 2 });
					if (["Date", "Datetime"].includes(fieldtype)) return frappe.datetime?.str_to_user?.(value) || value;
					return String(value);
				},
				rowKey(row, index) { return row?.name || row?.invoice || row?.batch_no || `row-${Number(this.result.start || 0) + index}`; },
				async refresh(resetPage = false) {
					if (!this.reportName) { this.error = __("No report was selected."); return; }
					if (resetPage) {
						this.pageStart = 0;
						this.comparison = null;
					}
					this.loading = true;
					this.error = "";
					this.chartInstance?.destroy?.();
					this.chartInstance = null;
					try {
						await this.loadCapabilities();
						if (this.capabilities.can_view === false) {
							this.result = { columns: [], rows: [], summary: [], chart: null, total: 0, start: 0, page_length: this.pageLength, has_previous: false, has_next: false, metadata: {} };
							this.error = __("This Advanced report is not included in the current Plan.");
							return;
						}
						const provider = this.resolveProvider();
						if (!provider?.load) throw new Error(__("No report provider is available."));
						this.result = await provider.load({ filters: this.reportFilters(), start: this.pageStart, page_length: this.pageLength });
						this.pageStart = Number(this.result.start || 0);
						this.updateLocation();
					} catch (error) {
						this.error = error?.message || error?._server_messages || __("The report could not be generated.");
					} finally {
						this.loading = false;
						await nextTick();
						this.renderChart();
					}
				},
				goToPage(pageNumber) {
					const page = Math.max(1, Number(pageNumber || 1));
					this.pageStart = (page - 1) * this.pageLength;
					this.refresh();
				},
				setPageSize(size) {
					this.pageLength = Math.min(100, Math.max(1, Number(size || VETEDGE_REPORT_PAGE_LENGTH)));
					this.pageStart = 0;
					this.refresh();
				},
				async loadComparison() {
					if (!this.comparisonSupported || this.comparisonLoading) return;
					if (!this.capabilities.advanced_features_entitled) {
						frappe.msgprint({
							title: __("Advanced Reporting"),
							message: __("Previous-period comparison is an Advanced reporting feature and is not included in the current Plan."),
							indicator: "orange",
						});
						return;
					}
					this.comparisonLoading = true;
					try {
						const response = await frappe.call(REPORT_COMPARISON_API, {
							report_name: this.reportName,
							filters: JSON.stringify(this.reportFilters()),
						});
						this.comparison = response.message || null;
					} catch (error) {
						this.comparison = null;
						frappe.msgprint({ title: __("Comparison Failed"), message: error?.message || __("The comparison could not be generated."), indicator: "red" });
					} finally {
						this.comparisonLoading = false;
						await nextTick();
						this.chartInstance?.destroy?.();
						this.chartInstance = null;
						this.renderChart();
					}
				},
				renderChart() {
					if (!this.result.chart?.data || !frappe.Chart || !this.$el) return;
					const target = this.$el.querySelector("[data-vetedge-report-chart]");
					if (!target) return;
					try { this.chartInstance = new frappe.Chart(target, { ...this.result.chart, height: 280 }); }
					catch (error) { console.warn("VetEdge report chart failed to render", error); }
				},
				back() { reportCenterRoute(this.sourceRoute || "/desk/vetedge-executive-dashboard"); },
				async runExport(options) {
					if (!this.capabilities.can_export) return;
					this.exportBusy = true;
					try {
						await window.VetEdgeReportProviders.downloadReportExport({ reportName: this.reportName, filters: this.reportFilters(), options, start: this.pageStart, pageLength: this.pageLength });
						frappe.show_alert?.({ message: __("Report download prepared successfully."), indicator: "green" });
					} catch (error) {
						frappe.msgprint({ title: __("Report Download Failed"), message: error?.message || __("The report could not be downloaded."), indicator: "red" });
					} finally {
						this.exportBusy = false;
					}
				},
				async runPrint() {
					if (!this.capabilities.can_print || this.printBusy || this.loading) return;
					this.printBusy = true;
					try {
						await window.VetEdgeReportProviders.printReport({
							reportName: this.reportName,
							filters: this.reportFilters(),
							options: { scope: "all_filtered" },
							start: this.pageStart,
							pageLength: this.pageLength,
						});
					} catch (error) {
						frappe.msgprint({ title: __("Report Print Failed"), message: error?.message || __("The report could not be prepared for printing."), indicator: "red" });
					} finally {
						this.printBusy = false;
					}
				},
				renderFilters() {
					const searchReport = this.filterSearchReportName();
					const smart = window.VetEdgeReportFilterUI.hasSmartDefinition(this.reportName);
					const branchSearcher = smart
						? (term) => this.searchReportFilter(searchReport, "branch", term)
						: (term) => this.searchGenericLink("Branch", term);
					const common = [
						h(EdgeLinkField, {
							modelValue: this.filters.branch,
							selectedLabel: this.filters.branch || __("All Branches"),
							label: __("Branch"),
							placeholder: __("All Branches"),
							searcher: branchSearcher,
							allowClear: true,
							"onUpdate:modelValue": (value) => this.setFilter("branch", value || ""),
						}),
						h(EdgeInput, { modelValue: this.filters.from_date, label: __("From Date"), type: "date", "onUpdate:modelValue": (value) => this.setFilter("from_date", value || "") }),
						h(EdgeInput, { modelValue: this.filters.to_date, label: __("To Date"), type: "date", "onUpdate:modelValue": (value) => this.setFilter("to_date", value || "") }),
					];
					const extra = window.VetEdgeReportFilterUI.extraNodes({
						h,
						EdgeLinkField,
						EdgeDropdown,
						reportName: this.reportName,
						filters: this.filters,
						searcher: (reportName, field, term) => this.searchReportFilter(reportName, field, term),
						onChange: (field, value) => this.setFilter(field, value),
					});
					return h("div", { class: "vetedge-report-center-filter-grid" }, [...common, ...extra]);
				},
				renderSavedViewActions() {
					return [
						h(EdgeDropdown, {
							class: "vetedge-report-center-saved-view",
							modelValue: this.selectedSavedViewId,
							options: this.savedViewOptions,
							placeholder: this.savedViewsLoading ? __("Loading saved views…") : __("Saved Views"),
							disabled: this.savedViewsLoading || this.capabilities.can_view === false,
							"onUpdate:modelValue": (value) => this.applySavedView(value || ""),
						}),
						h("button", { class: "edge-button edge-button--secondary", type: "button", disabled: this.capabilities.can_view === false, onClick: () => this.promptSaveView() }, __("Save View")),
						h("button", { class: "edge-button edge-button--secondary", type: "button", disabled: !this.selectedSavedView, onClick: () => this.promptSaveView(this.selectedSavedView) }, __("Rename")),
						h("button", { class: "edge-button edge-button--secondary", type: "button", disabled: !this.selectedSavedView, onClick: this.deleteSelectedSavedView }, __("Delete")),
					];
				},
				renderInsights() {
					const nodes = [];
					if (this.comparisonSupported && (this.comparison || this.comparisonLoading)) {
						const payload = this.comparison || {};
						nodes.push(h(EdgeReportComparisonPanel, {
							title: payload.title || __("Previous Period Comparison"),
							currentLabel: payload.current_label || __("Current period"),
							comparisonLabel: payload.comparison_label || __("Previous period"),
							metrics: payload.metrics || [],
							loading: this.comparisonLoading,
						}));
					}
					if (this.result.chart?.data) nodes.push(h("div", { class: "vetedge-report-center-chart", "data-vetedge-report-chart": "1" }));
					return h("div", { class: "vetedge-report-center-insights" }, nodes);
				},
			},
			render() {
				const reportShell = h(
					EdgeReportShell,
					{
						title: this.reportName || __("Veterinary Report"),
						eyebrow: __("Quick Report"),
						subtitle: __("EdgeSuite report view using the dashboard scope that opened this report."),
						columns: this.result.columns || [],
						rows: this.result.rows || [],
						summary: this.result.summary || [],
						pagination: this.pagination,
						loading: this.loading,
						error: this.error,
						rowKey: this.rowKey,
						formatter: this.formatValue,
						columnChooserEnabled: true,
						viewState: this.viewState,
						exportEnabled: Boolean(this.capabilities.can_export),
						printEnabled: Boolean(this.capabilities.can_print),
						exportBusy: this.exportBusy,
						printBusy: this.printBusy,
						exportInitialOptions: { format: "xlsx", scope: "all_filtered" },
						tier: this.capabilities.report_tier || "",
						subscriptionEntitled: this.capabilities.subscription_entitled !== false,
						emptyTitle: __("No report rows"),
						emptyDescription: __("No records match the selected report filters."),
						loadingMessage: __("Generating report…"),
						onRetry: () => this.refresh(),
						onPageChange: this.goToPage,
						onPageSizeChange: this.setPageSize,
						onViewStateChange: this.setViewState,
						onExport: this.runExport,
						onPrint: this.runPrint,
					},
					{
						actions: () => h("div", { class: "vetedge-report-center-actions" }, [
							h("span", { class: "vetedge-report-provider-badge" }, this.providerLabel),
							h("button", { class: "edge-button edge-button--secondary", type: "button", onClick: this.back }, __("Back to Dashboard")),
						]),
						filters: () => this.renderFilters(),
						filterActions: () => h("div", { class: "vetedge-report-center-actions" }, [
							...this.renderSavedViewActions(),
							...(this.comparisonSupported ? [h("button", {
								class: "edge-button edge-button--secondary",
								type: "button",
								disabled: this.loading || this.comparisonLoading || this.capabilities.can_view === false || !this.capabilities.advanced_features_entitled,
								title: this.capabilities.advanced_features_entitled ? __("Compare the selected period with the immediately preceding equal-length period.") : __("Advanced reporting feature"),
								onClick: this.loadComparison,
							}, this.comparisonLoading ? __("Comparing…") : (this.capabilities.advanced_features_entitled ? __("Compare Previous Period") : __("Compare · Advanced")))] : []),
							h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.loading || this.capabilities.can_view === false, onClick: () => this.refresh(true) }, this.loading ? __("Refreshing…") : __("Apply / Refresh")),
						]),
						chart: (this.result.chart?.data || this.comparison || this.comparisonLoading) ? () => this.renderInsights() : undefined,
						resultMeta: () => h("span", {}, __("{0} · filters and columns retained in URL", [this.providerLabel])),
					},
				);

				return h(EdgeAppShell, { product: "vetedge", title: "Veterinary", tenantName: profile.tenantName, branchName: this.filters.branch || profile.branchName, userName: profile.userName, activeRoute: this.sourceRoute || "/desk/vetedge-executive-dashboard" }, { default: () => reportShell });
			},
		};

		try {
			$loading.remove();
			const root = $("<div class='vetedge-report-center-root' data-edge-product='vetedge'></div>").appendTo(page.body);
			wrapper.vue_app = runtime.createEdgeApp(component);
			wrapper.vue_app.mount(root[0]);
		} catch (error) {
			console.error("Error mounting VetEdge Report Center:", error);
			fail(__("Error mounting Report Center: {0}", [error.message || String(error)]));
		}
	})));
};