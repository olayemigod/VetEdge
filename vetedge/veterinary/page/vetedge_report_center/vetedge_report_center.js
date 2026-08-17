const VETEDGE_REPORT_CENTER_STYLE_ID = "vetedge-report-center-style";
const VETEDGE_REPORT_PAGE_LENGTH = 50;

function ensureVetEdgeReportCenterStyles() {
	if (document.getElementById(VETEDGE_REPORT_CENTER_STYLE_ID)) return;
	const style = document.createElement("style");
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
		.vetedge-report-center-actions,.vetedge-report-center-pagination{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
		.vetedge-report-center-pagination{justify-content:space-between;border-top:1px solid var(--edge-color-border);padding-top:12px;color:var(--edge-color-ink-500);font-size:.85rem}
		.vetedge-report-provider-badge{display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;background:var(--edge-color-surface-muted);color:var(--edge-color-ink-500);font-size:.7rem;font-weight:600}
		:root[data-edge-palette] .vetedge-report-center-root .edge-shell-main{background:linear-gradient(180deg,var(--edge-color-brand-50) 0,var(--edge-color-surface-soft) 180px,var(--edge-color-surface-muted) 420px)!important}
		:root[data-edge-palette] .graph-svg-tip,:root[data-edge-appearance] .graph-svg-tip{background:var(--edge-color-surface)!important;border:1px solid var(--edge-color-border)!important;color:var(--edge-color-ink-950)!important}
		@media(max-width:900px){.vetedge-report-center-filter-grid,.vetedge-report-center-filter-grid--service{grid-template-columns:repeat(2,minmax(10rem,1fr))}.vetedge-report-center-root .edge-page-layout__content,.vetedge-report-center-root .edge-page-layout__header,.vetedge-report-center-root .edge-page-layout__filters{padding-left:18px;padding-right:18px}}
		@media(max-width:576px){.vetedge-report-center-filter-grid,.vetedge-report-center-filter-grid--service{grid-template-columns:1fr}.vetedge-report-center-root .edge-page-layout__content,.vetedge-report-center-root .edge-page-layout__header,.vetedge-report-center-root .edge-page-layout__filters{padding-left:12px;padding-right:12px}.vetedge-report-center-actions,.vetedge-report-center-actions .edge-button{width:100%}}
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
		const required = ["EdgeAppShell", "EdgePageLayout", "EdgePageHeader", "EdgeFilterBar", "EdgeLinkField", "EdgeDropdown", "EdgeInput", "EdgeDataTable", "EdgeDashboardLayout", "EdgeStatCard", "EdgeLoadingState", "EdgeErrorState", "EdgeEmptyState", "EdgeReportExportDialog"];
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
		const { EdgeAppShell, EdgePageLayout, EdgePageHeader, EdgeFilterBar, EdgeLinkField, EdgeDropdown, EdgeInput, EdgeDataTable, EdgeDashboardLayout, EdgeStatCard, EdgeLoadingState, EdgeErrorState, EdgeEmptyState, EdgeReportExportDialog } = runtime.components;
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
					result: { columns: [], rows: [], summary: [], chart: null, total: 0, start: 0, page_length: 0, has_previous: false, has_next: false, metadata: {} },
					chartInstance: null,
					exportOpen: false,
					exportBusy: false,
					printBusy: false,
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
			},
			methods: {
				async searchLink(doctype, term) {
					const response = await frappe.call("frappe.desk.search.search_link", { doctype, txt: term || "", page_length: 20, ignore_user_permissions: 0 });
					return response.message || [];
				},
				reportFilters() {
					return Object.fromEntries(Object.entries(this.filters).filter(([, value]) => value !== undefined && value !== null && String(value) !== ""));
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
				formatValue(value, fieldtype = "Data") {
					if (value === undefined || value === null || value === "") return "—";
					if (fieldtype === "Currency") {
						const currency = frappe.boot?.sysdefaults?.currency || "NGN";
						try { return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(Number(value || 0)); }
						catch (_error) { return `${currency} ${Number(value || 0).toLocaleString()}`; }
					}
					if (["Int", "Float", "Percent"].includes(fieldtype)) return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: fieldtype === "Int" ? 0 : 2 });
					if (["Date", "Datetime"].includes(fieldtype)) return frappe.datetime?.str_to_user?.(value) || value;
					return String(value);
				},
				displayRows() {
					return (this.result.rows || []).map((row, index) => {
						const output = { __row_key: row?.name || row?.invoice || row?.batch_no || `row-${this.result.start + index}` };
						for (const column of this.result.columns || []) output[column.fieldname] = this.formatValue(row?.[column.fieldname], column.fieldtype);
						return output;
					});
				},
				async refresh(resetPage = false) {
					if (!this.reportName) { this.error = __("No report was selected."); return; }
					if (resetPage) this.pageStart = 0;
					this.loading = true;
					this.error = "";
					this.chartInstance?.destroy?.();
					this.chartInstance = null;
					try {
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
				previousPage() { if (this.result.has_previous && !this.loading) { this.pageStart = Math.max(0, this.pageStart - this.pageLength); this.refresh(); } },
				nextPage() { if (this.result.has_next && !this.loading) { this.pageStart += this.pageLength; this.refresh(); } },
				renderChart() {
					if (!this.result.chart?.data || !frappe.Chart || !this.$el) return;
					const target = this.$el.querySelector("[data-vetedge-report-chart]");
					if (!target) return;
					try { this.chartInstance = new frappe.Chart(target, { ...this.result.chart, height: 280 }); }
					catch (error) { console.warn("VetEdge report chart failed to render", error); }
				},
				back() { reportCenterRoute(this.sourceRoute || "/desk/vetedge-executive-dashboard"); },
				async runExport(options) {
					this.exportBusy = true;
					try {
						await window.VetEdgeReportProviders.downloadReportExport({ reportName: this.reportName, filters: this.reportFilters(), options, start: this.pageStart, pageLength: this.pageLength });
						this.exportOpen = false;
						frappe.show_alert?.({ message: __("Report download prepared successfully."), indicator: "green" });
					} catch (error) {
						frappe.msgprint({ title: __("Report Download Failed"), message: error?.message || __("The report could not be downloaded."), indicator: "red" });
					} finally {
						this.exportBusy = false;
					}
				},
				async runPrint() {
					if (this.printBusy || this.loading) return;
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
				renderSummary() {
					if (!this.result.summary?.length) return null;
					return h(EdgeDashboardLayout, { minColumnWidth: "12rem", class: "vetedge-report-center-summary" }, { default: () => this.result.summary.map((card, index) => h(EdgeStatCard, { label: card.label || __("Metric"), value: this.formatValue(card.value, card.datatype || card.fieldtype || "Data"), tone: ["primary", "success", "warning", "info"][index % 4] })) });
				},
			},
			render() {
				const rows = this.displayRows();
				const layout = h(EdgePageLayout, {}, {
					header: () => h(EdgePageHeader, { eyebrow: __("Quick Report"), title: this.reportName || __("Veterinary Report"), subtitle: __("EdgeSuite report view using the dashboard scope that opened this report.") }, { actions: () => h("div", { class: "vetedge-report-center-actions" }, [
						h("span", { class: "vetedge-report-provider-badge" }, this.providerLabel),
						h("button", { class: "edge-button edge-button--secondary", type: "button", disabled: this.loading || this.printBusy, onClick: this.runPrint }, this.printBusy ? __("Preparing Print…") : __("Print")),
						h("button", { class: "edge-button edge-button--secondary", type: "button", disabled: this.loading, onClick: () => { this.exportOpen = true; } }, __("Download / Export")),
						h("button", { class: "edge-button edge-button--secondary", type: "button", onClick: this.back }, __("Back to Dashboard")),
					]) }),
					filters: () => h(EdgeFilterBar, { title: __("Report Filters") }, { default: () => this.renderFilters(), actions: () => h("div", { class: "vetedge-report-center-actions" }, [h("button", { class: "edge-button edge-button--primary", type: "button", disabled: this.loading, onClick: () => this.refresh(true) }, this.loading ? __("Refreshing…") : __("Apply / Refresh"))]) }),
					default: () => this.error
						? h("div", { class: "vetedge-report-center-content" }, [h(EdgeErrorState, { title: __("Report Failed"), message: this.error, onRetry: () => this.refresh() })])
						: this.loading
							? h("div", { class: "vetedge-report-center-content" }, [h(EdgeLoadingState, { message: __("Generating report…"), skeleton: true })])
							: h("div", { class: "vetedge-report-center-content" }, [
								this.renderSummary(),
								this.result.chart?.data ? h("section", { class: "vetedge-report-center-section" }, [h("div", { class: "vetedge-report-center-heading" }, [h("div", [h("span", __("Chart")), h("h2", this.result.chart.title || this.reportName)])]), h("div", { class: "vetedge-report-center-chart", "data-vetedge-report-chart": "1" })]) : null,
								h("section", { class: "vetedge-report-center-section" }, [
									h("div", { class: "vetedge-report-center-heading" }, [h("div", [h("span", __("Detail")), h("h2", this.reportName || __("Report Results")), h("p", __("Filters are retained in the URL and optimized providers load only the requested page."))])]),
									rows.length ? h(EdgeDataTable, { columns: this.result.columns || [], rows, rowKey: "__row_key" }) : h(EdgeEmptyState, { title: __("No report rows"), description: __("No records match the selected report filters.") }),
									(this.result.has_previous || this.result.has_next) ? h("div", { class: "vetedge-report-center-pagination" }, [h("span", {}, __("Showing {0}–{1} of {2}", [this.result.total ? this.result.start + 1 : 0, Math.min(this.result.start + rows.length, this.result.total), this.result.total])), h("div", { class: "vetedge-report-center-actions" }, [h("button", { class: "edge-button edge-button--compact", disabled: !this.result.has_previous || this.loading, onClick: this.previousPage }, __("Previous")), h("button", { class: "edge-button edge-button--compact", disabled: !this.result.has_next || this.loading, onClick: this.nextPage }, __("Next"))])]) : null,
								]),
							].filter(Boolean)),
				});
				const exportDialog = h(EdgeReportExportDialog, { open: this.exportOpen, busy: this.exportBusy, reportTitle: this.reportName || __("Veterinary Report"), columns: this.result.columns || [], initialOptions: { format: "xlsx", scope: "all_filtered" }, onClose: () => { if (!this.exportBusy) this.exportOpen = false; }, onExport: this.runExport });
				return h(EdgeAppShell, { product: "vetedge", title: "Veterinary", tenantName: profile.tenantName, branchName: this.filters.branch || profile.branchName, userName: profile.userName, activeRoute: this.sourceRoute || "/desk/vetedge-executive-dashboard" }, { default: () => [layout, exportDialog] });
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