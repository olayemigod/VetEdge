import { h, nextTick } from "vue";

const HOST_STYLE_ID = "vetedge-shared-dashboard-host-style";
const HOST_STYLE_URL = "/assets/vetedge/css/vetedge_shared_dashboard_host.css?v=20260812-3";
const DASHBOARD_API = "vetedge.services.reporting_logic_v5.get_dashboard_payload";
const BRANCH_SEARCH_API = "vetedge.services.dashboard_filter_search.search_dashboard_branches";
const BRANCH_SEARCH_PAGE_LENGTH = 20;

function getRuntime() {
	return window.EdgeSuiteUI || window.EdgeUI || null;
}

function ensureHostStyles() {
	if (document.getElementById(HOST_STYLE_ID)) return;
	const link = document.createElement("link");
	link.id = HOST_STYLE_ID;
	link.rel = "stylesheet";
	link.href = HOST_STYLE_URL;
	document.head.appendChild(link);
}

function deskRoute(route) {
	const raw = String(route || "").trim();
	if (!raw) return "";
	try {
		const url = new URL(raw, window.location.origin);
		if (url.pathname === "/app" || url.pathname.startsWith("/app/")) {
			url.pathname = `/desk${url.pathname.slice(4)}`;
		}
		return `${url.pathname}${url.search}${url.hash}`;
	} catch (_error) {
		return raw.replace(/^\/app(?=\/|$)/, "/desk");
	}
}

function currentProfile() {
	const boot = window.frappe?.boot || {};
	const user = window.frappe?.session?.user || "";
	const info = boot.user_info?.[user] || {};
	const identity = boot.edgesuite_ui_identity?.vetedge || boot.vetedge_ui_identity || {};
	return {
		tenantName: identity.tenant_name || boot.sysdefaults?.company || "",
		branchName:
			boot.edgesuite_product_menu?.branch ||
			window.frappe?.defaults?.get_user_default?.("branch") ||
			"All Branches",
		userName: info.fullname || info.full_name || user,
	};
}

function datePresetOptions() {
	const options = window.frappe?.EdgeSuite?.DateRanges?.getOptions?.() || [];
	if (Array.isArray(options) && options.length) {
		return options.map((option) =>
			typeof option === "string" ? { value: option, label: option } : option,
		);
	}
	return [
		{ value: "today", label: "Today" },
		{ value: "this_week", label: "This Week" },
		{ value: "this_month", label: "This Month" },
		{ value: "this_quarter", label: "This Quarter" },
		{ value: "this_year", label: "This Year" },
		{ value: "custom", label: "Custom Period" },
	];
}

function initialFilters() {
	const routeOptions = window.frappe?.route_options || {};
	const dateRanges = window.frappe?.EdgeSuite?.DateRanges;
	const preset = routeOptions.date_preset || dateRanges?.getDefaultPreset?.() || "this_month";
	let fromDate = routeOptions.from_date || "";
	let toDate = routeOptions.to_date || "";
	if (!fromDate || !toDate) {
		const range = dateRanges?.getRange?.(preset);
		fromDate = range?.start || window.frappe?.datetime?.month_start?.() || "";
		toDate = range?.end || window.frappe?.datetime?.get_today?.() || "";
	}
	return {
		branch: routeOptions.branch || "",
		date_preset: preset,
		from_date: fromDate,
		to_date: toDate,
	};
}

function openRoute(route) {
	const professional = window.VetEdgeProfessionalUI;
	if (typeof professional?.openRoute === "function") return professional.openRoute(route);
	const adapter = getRuntime()?.getAdapter?.("navigation:vetedge");
	if (adapter?.open?.(route) === true) return true;
	window.location.assign(deskRoute(route));
	return true;
}

function call(method, args = {}) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method,
			args,
			callback: (response) => resolve(response.message || {}),
			error: reject,
		});
	});
}

function cssToken(name, fallback) {
	const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	return value || fallback;
}

function themeChartPalette() {
	return [
		cssToken("--edge-color-brand-600", "#2563eb"),
		cssToken("--edge-color-success", "#16a34a"),
		cssToken("--edge-color-accent", "#7c3aed"),
		cssToken("--edge-color-warning", "#d97706"),
		cssToken("--edge-color-info", "#0891b2"),
		cssToken("--edge-color-danger", "#dc2626"),
		cssToken("--edge-color-brand-400", "#60a5fa"),
		cssToken("--edge-color-accent-strong", "#0f766e"),
	];
}

function formatCurrency(value) {
	const currency = frappe.boot?.sysdefaults?.currency || "NGN";
	try {
		return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value || 0));
	} catch (_error) {
		return `${currency} ${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
	}
}

function formatMetric(card = {}) {
	const type = String(card.value_type || card.fieldtype || "").toLowerCase();
	const value = card.value;
	if (type === "currency") return formatCurrency(value);
	if (type === "percent" && Number.isFinite(Number(value))) return `${Number(value).toFixed(1)}%`;
	if (type === "float" && Number.isFinite(Number(value))) return Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
	if (type === "int" || type === "integer") return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
	return value ?? 0;
}

function chartHasData(chart) {
	const labels = chart?.data?.labels || [];
	const datasets = chart?.data?.datasets || [];
	return Boolean(labels.length && datasets.some((dataset) => Array.isArray(dataset.values) && dataset.values.length));
}

function createDashboardComponent(page, config, runtime) {
	const {
		EdgeAppShell,
		EdgePageLayout,
		EdgePageHeader,
		EdgeFilterBar,
		EdgeLinkField,
		EdgeDropdown,
		EdgeInput,
		EdgeDashboardLayout,
		EdgeStatCard,
		EdgeDataTable,
		EdgeStatusBadge,
		EdgeLoadingState,
		EdgeErrorState,
		EdgeEmptyState,
	} = runtime.components;
	const profile = currentProfile();
	const activeRoute = deskRoute(config.route || window.location.pathname || "");

	return {
		name: "VetEdgeSharedDashboardHost",
		data() {
			return {
				loading: false,
				error: "",
				payload: {
					kpis: [],
					charts: [],
					report_links: [],
					supporting_tables: [],
					alerts: [],
					collection_metrics: [],
					revenue_composition: [],
					health_indicators: [],
				},
				filters: initialFilters(),
				datePresets: datePresetOptions(),
				reportsOpen: false,
				chartInstances: [],
			};
		},
		mounted() {
			this.refresh();
			window.EdgeSuiteNavigation?.syncActiveSection?.(
				this.$el?.closest?.(".edge-app-shell") || document.querySelector(".edge-app-shell"),
			);
		},
		beforeUnmount() {
			this.destroyCharts();
		},
		methods: {
			searchBranches(term = "") {
				return call(BRANCH_SEARCH_API, {
					dashboard_key: config.key,
					txt: term || "",
					page_length: BRANCH_SEARCH_PAGE_LENGTH,
				});
			},
			setBranch(value) {
				this.filters.branch = value || "";
			},
			setPreset(value) {
				this.filters.date_preset = value || "custom";
				if (this.filters.date_preset !== "custom") {
					const range = frappe.EdgeSuite?.DateRanges?.getRange?.(this.filters.date_preset);
					if (range) {
						this.filters.from_date = range.start || "";
						this.filters.to_date = range.end || "";
					}
				}
			},
			setDate(fieldname, value) {
				this.filters[fieldname] = value || "";
				this.filters.date_preset = "custom";
			},
			async refresh() {
				this.loading = true;
				this.error = "";
				this.reportsOpen = false;
				frappe.route_options = { ...this.filters };
				try {
					this.payload = (await call(DASHBOARD_API, {
						dashboard_key: config.key,
						filters: this.filters,
					})) || this.payload;
					await nextTick();
					this.renderCharts();
				} catch (error) {
					this.error = error?.message || __("Unable to load dashboard data.");
				} finally {
					this.loading = false;
					await nextTick();
					this.renderCharts();
				}
			},
			openReport(report, extraFilters = {}) {
				if (!report) return;
				this.reportsOpen = false;
				frappe.route_options = {
					...this.filters,
					...extraFilters,
				};
				frappe.set_route("query-report", report);
			},
			openAction(action) {
				if (action?.type === "report" && action.target) this.openReport(action.target, action.filters || {});
			},
			destroyCharts() {
				this.chartInstances.forEach((instance) => instance?.destroy?.());
				this.chartInstances = [];
			},
			renderChart(target, chart, paletteOffset = 0) {
				if (!target || !chartHasData(chart) || !frappe.Chart) return;
				const palette = themeChartPalette();
				const datasetCount = Math.max(1, chart.data?.datasets?.length || 1);
				const colors = Array.from({ length: Math.max(datasetCount, chart.data?.labels?.length || 1) }, (_item, index) =>
					palette[(index + paletteOffset) % palette.length],
				);
				try {
					const instance = new frappe.Chart(target, {
						title: "",
						data: chart.data,
						type: chart.type || "bar",
						colors,
						barOptions: chart.barOptions || { stacked: 0 },
						height: 280,
						tooltipOptions: {
							formatTooltipY: (value) => formatMetric({ value, ...chart }),
						},
					});
					this.chartInstances.push(instance);
				} catch (error) {
					console.warn("VetEdge EdgeSuite chart failed to render", error);
				}
			},
			renderCharts() {
				this.destroyCharts();
				const root = this.$el;
				if (!root) return;
				if (this.payload.revenue_composition?.length) {
					const composition = this.payload.revenue_composition;
					this.renderChart(root.querySelector("[data-edge-chart='revenue-composition']"), {
						type: "donut",
						value_type: "currency",
						data: {
							labels: composition.map((row) => row.label || row.title),
							datasets: [{ name: __("Revenue"), values: composition.map((row) => Number(row.value || 0)) }],
						},
					});
				}
				(this.payload.charts || []).forEach((chart, index) => {
					this.renderChart(root.querySelector(`[data-edge-chart-index='${index}']`), chart, index);
				});
			},
			renderFilters() {
				return h("div", { class: "vetedge-shared-dashboard-filter-grid" }, [
					h(EdgeLinkField, {
						modelValue: this.filters.branch,
						selectedLabel: this.filters.branch || __("All Branches"),
						label: __("Branch"),
						placeholder: __("Search branches"),
						searcher: this.searchBranches,
						allowClear: true,
						"onUpdate:modelValue": this.setBranch,
					}),
					h(EdgeDropdown, {
						modelValue: this.filters.date_preset,
						label: __("Period"),
						options: this.datePresets,
						"onUpdate:modelValue": this.setPreset,
					}),
					h(EdgeInput, {
						modelValue: this.filters.from_date,
						label: __("From Date"),
						type: "date",
						disabled: this.filters.date_preset !== "custom",
						"onUpdate:modelValue": (value) => this.setDate("from_date", value),
					}),
					h(EdgeInput, {
						modelValue: this.filters.to_date,
						label: __("To Date"),
						type: "date",
						disabled: this.filters.date_preset !== "custom",
						"onUpdate:modelValue": (value) => this.setDate("to_date", value),
					}),
				]);
			},
			renderFilterActions() {
				const actions = [
					h(
						"button",
						{
							class: "edge-button edge-button--primary edge-primary-button",
							type: "button",
							disabled: this.loading,
							onClick: () => this.refresh(),
						},
						this.loading ? __("Refreshing…") : __("Apply / Refresh"),
					),
				];
				if (this.payload.report_links?.length) {
					actions.push(
						h("div", { class: "vetedge-dashboard-quick-reports" }, [
							h(
								"button",
								{
									class: "edge-button edge-button--secondary edge-secondary-button",
									type: "button",
									"aria-haspopup": "menu",
									"aria-expanded": this.reportsOpen ? "true" : "false",
									onClick: () => {
										this.reportsOpen = !this.reportsOpen;
									},
								},
								__("Quick Reports") + " ▾",
							),
							this.reportsOpen
								? h(
									"div",
									{ class: "vetedge-dashboard-quick-reports-menu", role: "menu" },
									this.payload.report_links.map((link) =>
										h(
											"button",
											{
												class: "vetedge-dashboard-quick-report-item",
												type: "button",
												role: "menuitem",
												onClick: () => this.openReport(link.report),
											},
											link.label || link.report,
										),
									),
								)
								: null,
						]),
					);
				}
				return h("div", { class: "vetedge-shared-dashboard-filter-actions" }, actions);
			},
			renderStatCard(card, index = 0) {
				const component = h(EdgeStatCard, {
					label: card.label || card.title || "Metric",
					value: formatMetric(card),
					helper: card.secondary_value || card.helper || "",
					tone: card.severity || ["primary", "success", "warning", "info", "neutral"][index % 5],
					tooltip: card.tooltip || "",
				});
				const progress = String(card.value_type || "").toLowerCase() === "percent"
					? h("div", { class: "edge-progress", role: "progressbar", "aria-valuenow": Number(card.value || 0), "aria-valuemin": 0, "aria-valuemax": 100 }, [
						h("span", { class: "edge-progress__bar", style: { width: `${Math.min(100, Math.max(0, Number(card.value || 0)))}%` } }),
					])
					: null;
				const content = h("div", { class: "vetedge-edge-stat-wrap" }, [component, progress]);
				if (!card.action) return content;
				return h(
					"button",
					{
						class: "vetedge-edge-stat-action",
						type: "button",
						onClick: () => this.openAction(card.action),
					},
					[content],
				);
			},
			renderCardSection(title, eyebrow, cards) {
				if (!cards?.length) return null;
				return h("section", { class: "vetedge-edge-dashboard-section" }, [
					h("header", { class: "vetedge-edge-dashboard-section__heading" }, [
						h("div", [
							eyebrow ? h("span", eyebrow) : null,
							h("h2", title),
						]),
					]),
					h(
						EdgeDashboardLayout,
						{ minColumnWidth: "12rem" },
						{ default: () => cards.map((card, index) => this.renderStatCard(card, index)) },
					),
				]);
			},
			renderAlerts() {
				if (!this.payload.alerts?.length) return null;
				return h(
					"section",
					{ class: "vetedge-edge-alerts", "aria-label": __("Dashboard alerts") },
					this.payload.alerts.map((alert) =>
						h("article", { class: ["vetedge-edge-alert", `is-${alert.severity || "info"}`] }, [
							h("div", { class: "vetedge-edge-alert__copy" }, [
								h("strong", alert.title || __("Attention")),
								h("p", alert.description || ""),
							]),
							h("div", { class: "vetedge-edge-alert__actions" }, [
								alert.supporting_metric
									? h(EdgeStatusBadge, { label: String(alert.supporting_metric), tone: alert.severity || "info" })
									: null,
								alert.action
									? h("button", { class: "edge-button edge-button--compact", type: "button", onClick: () => this.openAction(alert.action) }, __("View Details"))
									: null,
							]),
						]),
					),
				);
			},
			renderRevenueComposition() {
				const composition = this.payload.revenue_composition || [];
				if (!composition.length) return null;
				const rows = composition.map((row) => ({
					service: row.label || row.title,
					revenue: formatMetric({ value: row.value, value_type: "currency" }),
					share: `${Number(row.share_percent || 0).toFixed(1)}%`,
				}));
				return h("section", { class: "vetedge-edge-dashboard-section" }, [
					h("header", { class: "vetedge-edge-dashboard-section__heading" }, [
						h("div", [h("span", __("Revenue Mix")), h("h2", __("Revenue Composition"))]),
						h("button", { class: "edge-button edge-button--secondary", type: "button", onClick: () => this.openReport("Service Revenue Breakdown") }, __("View Service Revenue Report")),
				]),
					h("div", { class: "vetedge-edge-composition-grid" }, [
						h("article", { class: "vetedge-edge-chart-card" }, [
							h("div", { class: "vetedge-edge-chart", "data-edge-chart": "revenue-composition" }),
						]),
						h(EdgeDataTable, {
							columns: [
								{ fieldname: "service", label: __("Service Line") },
								{ fieldname: "revenue", label: __("Revenue") },
								{ fieldname: "share", label: __("Share") },
							],
							rows,
							rowKey: "service",
							compact: true,
						}),
					]),
				]);
			},
			renderChartsSection() {
				const charts = this.payload.charts || [];
				if (!charts.length) return null;
				return h("section", { class: "vetedge-edge-dashboard-section" }, [
					h("header", { class: "vetedge-edge-dashboard-section__heading" }, [
						h("div", [h("span", __("Trends")), h("h2", __("Performance Trends"))]),
					]),
					h(
						"div",
						{ class: "vetedge-edge-chart-grid" },
						charts.map((chart, index) =>
							h("article", { class: "vetedge-edge-chart-card" }, [
								h("header", [h("h3", chart.title || __("Chart"))]),
								chartHasData(chart)
									? h("div", { class: "vetedge-edge-chart", "data-edge-chart-index": String(index) })
									: h(EdgeEmptyState, { title: __("No chart data"), description: chart.empty_state || __("No values are available for this metric in the selected range.") }),
							]),
						),
					),
				]);
			},
			renderSupportingTables() {
				const tables = this.payload.supporting_tables || [];
				if (!tables.length) return null;
				return tables.map((table) => {
					const currencyFields = new Set((table.columns || []).filter((column) => String(column.fieldtype).toLowerCase() === "currency").map((column) => column.fieldname));
					const rows = (table.rows || []).map((row) => {
						const next = { ...row };
						currencyFields.forEach((fieldname) => {
							next[fieldname] = formatCurrency(row[fieldname]);
						});
						return next;
					});
					const columns = (table.columns || []).map((column) => ({ ...column, fieldtype: currencyFields.has(column.fieldname) ? "Data" : column.fieldtype }));
					return h("section", { class: "vetedge-edge-dashboard-section", key: table.title }, [
						h("header", { class: "vetedge-edge-dashboard-section__heading" }, [
							h("div", [
								h("span", __("Detail")),
								h("h2", table.title || __("Performance Detail")),
								table.description ? h("p", table.description) : null,
							]),
						]),
						h(EdgeDataTable, {
							columns,
							rows,
							rowKey: table.row_key || "name",
							emptyTitle: __("No detail rows"),
							emptyDescription: __("No matching rows were found for the selected range."),
						}),
					]);
				});
			},
			renderOutstanding() {
				const groups = this.payload.outstanding_breakdowns;
				if (!groups) return null;
				const definitions = [
					["by_branch", __("Outstanding by Branch")],
					["by_service", __("Outstanding by Service")],
					["by_customer", __("Outstanding by Customer")],
					["by_doctor", __("Outstanding by Practitioner")],
				];
				const tables = definitions
					.map(([key, title]) => ({ title, rows: groups[key] || [] }))
					.filter((table) => table.rows.length);
				if (!tables.length) return null;
				return h("section", { class: "vetedge-edge-dashboard-section" }, [
					h("header", { class: "vetedge-edge-dashboard-section__heading" }, [
						h("div", [h("span", __("Receivables")), h("h2", __("Outstanding Insights"))]),
					]),
					h("div", { class: "vetedge-edge-table-grid" }, tables.map((table) =>
						h("article", { class: "vetedge-edge-table-card" }, [
							h("h3", table.title),
							h(EdgeDataTable, {
								columns: [
									{ fieldname: "name", label: __("Name") },
									{ fieldname: "display_value", label: __("Outstanding") },
								],
								rows: table.rows.map((row) => ({ ...row, display_value: formatCurrency(row.value) })),
								rowKey: "name",
								compact: true,
							}),
						]),
					)),
				]);
			},
			renderContent() {
				if (this.error) return h(EdgeErrorState, { title: __("Dashboard Fetch Failed"), message: this.error, onRetry: () => this.refresh() });
				if (this.loading && !this.payload.kpis?.length) return h(EdgeLoadingState, { message: __("Loading dashboard data…"), skeleton: true });
				const sections = [
					this.renderAlerts(),
					this.renderCardSection(__("Executive Summary"), __("Overview"), this.payload.kpis),
					this.renderCardSection(__("Collection Performance"), __("Collections"), this.payload.collection_metrics),
					this.renderRevenueComposition(),
					this.renderCardSection(__("Financial Health & Concentration"), __("Health"), this.payload.health_indicators),
					this.renderOutstanding(),
					this.renderChartsSection(),
					...(this.renderSupportingTables() || []),
				].filter(Boolean);
				if (!sections.length) return h(EdgeEmptyState, { title: __("No dashboard data"), description: __("No information was found for the selected filters.") });
				return h("div", { class: "vetedge-edge-dashboard-content" }, sections);
			},
		},
		render() {
			return h(
				EdgeAppShell,
				{
					product: "vetedge",
					title: "Veterinary",
					tenantName: profile.tenantName,
					branchName: this.filters.branch || profile.branchName,
					userName: profile.userName,
					activeRoute,
					onNavigate: openRoute,
				},
				{
					default: () => h(
						EdgePageLayout,
						null,
						{
							header: () => h(EdgePageHeader, {
								eyebrow: __("Veterinary Performance"),
								title: config.title || this.payload.title || __("Veterinary Dashboard"),
								subtitle: config.subtitle || __("Branch-aware veterinary operational and performance insights."),
							}),
							filters: () => h(
								EdgeFilterBar,
								{ title: __("Dashboard Filters") },
								{
									default: () => this.renderFilters(),
									actions: () => this.renderFilterActions(),
								},
							),
							default: () => this.renderContent(),
						},
					),
				},
			);
		},
	};
}

function showFailure(page, message) {
	$(page.body).empty();
	$("<div class=\"alert alert-danger p-6 text-center\"></div>")
		.text(message || __("The dashboard failed to load."))
		.appendTo(page.body);
}

function installDashboard(wrapper, config) {
	ensureHostStyles();
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __(config.title || "Veterinary Dashboard"),
		single_column: true,
	});
	wrapper.page = page;

	$(page.body).empty();
	const loading = $("<div class=\"p-6 text-center text-muted\"></div>")
		.text(__("Loading EdgeSuite dashboard shell..."))
		.appendTo(page.body);

	const requiredComponents = [
		"EdgeAppShell",
		"EdgePageLayout",
		"EdgePageHeader",
		"EdgeFilterBar",
		"EdgeLinkField",
		"EdgeDropdown",
		"EdgeInput",
		"EdgeDashboardLayout",
		"EdgeStatCard",
		"EdgeDataTable",
		"EdgeStatusBadge",
		"EdgeLoadingState",
		"EdgeErrorState",
		"EdgeEmptyState",
	];
	frappe.require("edgeui.bundle.js", () => {
		const runtime = getRuntime();
		const components = runtime?.components || runtime;
		const missing = requiredComponents.filter((name) => !components?.[name]);
		if (!runtime?.createEdgeApp || missing.length) {
			loading.remove();
			showFailure(
				page,
				missing.length
					? __("Missing EdgeSuite UI components: {0}", [missing.join(", ")])
					: __("The standalone EdgeSuite UI runtime is unavailable."),
			);
			return;
		}

		const mountDashboard = () => {
			const professional = window.VetEdgeProfessionalUI?.install?.();
			if (!professional?.installed) {
				loading.remove();
				showFailure(page, professional?.message || __("VetEdge requires the shared EdgeSuite professional shell."));
				return;
			}
			try {
				loading.remove();
				$(page.body).empty();
				const root = $('<div class="vetedge-shared-dashboard-root" data-edge-product="vetedge"></div>').appendTo(page.body);
				const component = createDashboardComponent(page, config, runtime);
				wrapper.edge_dashboard_app?.unmount?.();
				wrapper.edge_dashboard_app = runtime.createEdgeApp(component);
				wrapper.edge_dashboard_view = wrapper.edge_dashboard_app.mount(root[0]);
			} catch (error) {
				console.error("Unable to mount shared VetEdge dashboard shell", error);
				showFailure(page, error?.message || String(error));
			}
		};

		if (window.VetEdgeProfessionalUI?.install) mountDashboard();
		else frappe.require("/assets/vetedge/js/vetedge_professional_ui.js", mountDashboard);
	});

	return page;
}

export function mountVetEdgeDashboardHost(wrapper, config = {}) {
	if (!wrapper) throw new Error("A Frappe page wrapper is required.");
	return installDashboard(wrapper, config);
}

if (typeof window !== "undefined") window.mountVetEdgeDashboardHost = mountVetEdgeDashboardHost;

export default mountVetEdgeDashboardHost;
