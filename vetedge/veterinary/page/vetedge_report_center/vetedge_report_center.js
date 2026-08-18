const VETEDGE_REPORT_CENTER_STYLE_ID = "vetedge-report-center-style";
const VETEDGE_REPORT_PAGE_LENGTH = 50;
const CAPABILITIES_API = "vetedge.services.reporting_capabilities.get_shell_capabilities";

function ensureVetEdgeReportCenterStyles() {
	if (document.getElementById(VETEDGE_REPORT_CENTER_STYLE_ID)) return;
	const style = document.createElement("style");
	style.id = VETEDGE_REPORT_CENTER_STYLE_ID;
	style.textContent = `
		.vetedge-report-center-root,.vetedge-report-center-root .edge-app-shell,.vetedge-report-center-root .edge-shell-body,.vetedge-report-center-root .edge-shell-main,.vetedge-report-center-root .edge-page-layout{width:100%;max-width:none;min-width:0}
		.vetedge-report-center-filter-grid{display:grid;grid-template-columns:repeat(3,minmax(12rem,1fr));gap:14px;width:100%;align-items:end}
		.vetedge-report-center-filter-grid--service{grid-template-columns:repeat(3,minmax(11rem,1fr))}
		.vetedge-report-center-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
		.vetedge-report-provider-badge{display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;background:var(--edge-color-surface-muted);color:var(--edge-color-ink-500);font-size:.7rem;font-weight:600}
		.vetedge-report-center-chart{min-height:280px}
		:root[data-edge-palette] .vetedge-report-center-root .edge-shell-main{background:linear-gradient(180deg,var(--edge-color-brand-50) 0,var(--edge-color-surface-soft) 180px,var(--edge-color-surface-muted) 420px)!important}
		:root[data-edge-palette] .graph-svg-tip,:root[data-edge-appearance] .graph-svg-tip{background:var(--edge-color-surface)!important;border:1px solid var(--edge-color-border)!important;color:var(--edge-color-ink-950)!important}
		@media(max-width:900px){.vetedge-report-center-filter-grid,.vetedge-report-center-filter-grid--service{grid-template-columns:repeat(2,minmax(10rem,1fr))}}
		@media(max-width:576px){.vetedge-report-center-filter-grid,.vetedge-report-center-filter-grid--service{grid-template-columns:1fr}.vetedge-report-center-actions,.vetedge-report-center-actions .edge-button{width:100%}}
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

function reportCenterParams() {
	const params = new URLSearchParams(window.location.search || "");
	const routeOptions = frappe.route_options || {};
	const get = (key, fallback = "") => params.get(key) || routeOptions[key] || fallback;
	return {
		report: get("report"),
		source: get("source", "/desk/vetedge-executive-dashboard"),
		branch: get("branch"),
		from_date: get("from_date"),
		to_date: get("to_date"),
		date_preset: get("date_preset"),
		customer: get("customer"),
		practitioner: get("practitioner"),
		service_category: get("service_category"),
		item: get("item"),
	};
}

function loadProviderAssets(callback) {
	frappe.require("/assets/vetedge/js/vetedge_report_provider_adapter.js", () => {
		frappe.require("/assets/vetedge/js/vetedge_report_provider_registry.js", () => {
			window.VetEdgeReportProviderRegistry?.register?.();
			callback();
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
		if (!runtime?.createEdgeApp || !runtime?.Vue?.h || missing.length) {
			fail(__("Quick Reports require the current EdgeSuite UI runtime. Missing: {0}", [missing.join(", ")]));
			return;
		}

		window.VetEdgeProfessionalUI?.install?.();
		window.VetEdgeUIBridge?.install?.();
		window.VetEdgeNavigationRecovery?.install?.();
		const h = runtime.Vue.h;
		const nextTick = runtime.Vue.nextTick;
		const { EdgeAppShell, EdgeReportShell, EdgeLinkField, EdgeDropdown, EdgeInput } = runtime.components;
		const initial = reportCenterParams();
		const profile = reportCenterProfile();
		const serviceCategories = ["", "Consultation Service", "Treatment", "Registration", "Vaccination", "Lab", "Grooming", "Boarding", "Hospitalisation", "Dispensary / Pharmacy", "General / Other"].map((value) => ({ value, label: value || __("All Service Categories") }));

		const component = {
			name: "VetEdgeReportCenter",
			data() {
				return {
					reportName: initial.report,
					sourceRoute: initial.source,
					filters: { branch: initial.branch || "", from_date: initial.from_date || "", to_date: initial.to_date || "", date_preset: initial.date_preset || "", customer: initial.customer || "", practitioner: initial.practitioner || "", service_category: initial.service_category || "", item: initial.item || "" },
					loading: false,
					error: "",
					provider: null,
					pageStart: 0,
					pageLength: VETEDGE_REPORT_PAGE_LENGTH,
					result: { columns: [], rows: [], summary: [], chart: null, total: 0, start: 0, page_length: VETEDGE_REPORT_PAGE_LENGTH, has_previous: false, has_next: false, metadata: {} },
					chartInstance: null,
					exportBusy: false,
					printBusy: false,
					capabilities: { can_view: true, can_print: false, can_export: false, report_tier: "", subscription_entitled: true },
				};
			},
			mounted() { this.refresh(); },
			beforeUnmount() { this.chartInstance?.destroy?.(); },
			computed: {
				isServiceRevenue() { return this.reportName === "Service Revenue Breakdown"; },
				providerLabel() {
					if (!this.provider) return __("Query Report");
					if (["query-level", "query-level-detail"].includes(this.result.metadata?.pagination_mode)) return __("Optimized paginated provider");
					if (this.result.metadata?.pagination_mode === "materialize-then-slice") return __("Paged response · optimization pending");
					return this.provider.kind === "paginated" ? __("Paginated provider") : __("Query Report provider");
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
				async searchLink(doctype, term) {
					const response = await frappe.call("frappe.desk.search.search_link", { doctype, txt: term || "", page_length: 20, ignore_user_permissions: 0 });
					return response.message || [];
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
						this.capabilities = { can_view: true, can_print: false, can_export: false, report_tier: "", subscription_entitled: true };
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
					window.history.replaceState({}, "", `/desk/vetedge-report-center?${params.toString()}`);
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
					if (resetPage) this.pageStart = 0;
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
					const common = [
						h(EdgeLinkField, { modelValue: this.filters.branch, selectedLabel: this.filters.branch || __("All Branches"), label: __("Branch"), placeholder: __("All Branches"), searcher: (term) => this.searchLink("Branch", term), allowClear: true, "onUpdate:modelValue": (value) => { this.filters.branch = value || ""; } }),
						h(EdgeInput, { modelValue: this.filters.from_date, label: __("From Date"), type: "date", "onUpdate:modelValue": (value) => { this.filters.from_date = value || ""; } }),
						h(EdgeInput, { modelValue: this.filters.to_date, label: __("To Date"), type: "date", "onUpdate:modelValue": (value) => { this.filters.to_date = value || ""; } }),
					];
					if (!this.isServiceRevenue) return h("div", { class: "vetedge-report-center-filter-grid" }, common);
					return h("div", { class: "vetedge-report-center-filter-grid vetedge-report-center-filter-grid--service" }, [
						...common,
						h(EdgeDropdown, { modelValue: this.filters.service_category, label: __("Service Category"), options: serviceCategories, "onUpdate:modelValue": (value) => { this.filters.service_category = value || ""; } }),
						h(EdgeInput, { modelValue: this.filters.practitioner, label: __("Practitioner"), placeholder: __("All Practitioners"), "onUpdate:modelValue": (value) => { this.filters.practitioner = value || ""; } }),
						h(EdgeLinkField, { modelValue: this.filters.item, selectedLabel: this.filters.item, label: __("Item"), placeholder: __("All Items"), searcher: (term) => this.searchLink("Item", term), allowClear: true, "onUpdate:modelValue": (value) => { this.filters.item = value || ""; } }),
					]);
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
							h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.loading || this.capabilities.can_view === false, onClick: () => this.refresh(true) }, this.loading ? __("Refreshing…") : __("Apply / Refresh")),
						]),
						chart: this.result.chart?.data ? () => h("div", { class: "vetedge-report-center-chart", "data-vetedge-report-chart": "1" }) : undefined,
						resultMeta: () => h("span", {}, __("{0} · filters retained in URL", [this.providerLabel])),
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