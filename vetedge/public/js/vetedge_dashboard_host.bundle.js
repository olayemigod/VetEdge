import { h } from "vue";

const HOST_STYLE_ID = "vetedge-shared-dashboard-host-style";
const HOST_STYLE_URL = "/assets/vetedge/css/vetedge_shared_dashboard_host.css?v=20260812-2";
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
		{ value: "last_30_days", label: "Last 30 Days" },
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

function createVirtualField(view, definition) {
	const fieldname = definition.fieldname;
	if (!(fieldname in view.filters)) view.filters[fieldname] = definition.default ?? "";
	const field = {
		df: { ...definition },
		get_value() {
			return view.filters[fieldname] ?? "";
		},
		set_value(value) {
			view.filters[fieldname] = value ?? "";
			view.$forceUpdate?.();
			if (typeof definition.change === "function") return definition.change.call(field);
			return value;
		},
		refresh() {
			view.$forceUpdate?.();
		},
	};
	view._filterFields[fieldname] = field;
	return field;
}

function pageProxy(page, body, view) {
	const proxy = Object.create(page || null);
	proxy.body = body;
	proxy.edgeSuiteEmbedded = true;
	proxy.set_title = typeof page?.set_title === "function" ? page.set_title.bind(page) : () => {};
	proxy.add_field = (definition) => createVirtualField(view, definition);
	proxy.set_primary_action = (label, action) => {
		view.primaryActionLabel = label || __("Apply / Refresh");
		view.primaryAction = typeof action === "function" ? action : null;
		return action;
	};
	proxy.clear_primary_action = () => {
		view.primaryAction = null;
		view.primaryActionLabel = __("Apply / Refresh");
	};
	return proxy;
}

function openRoute(route) {
	const professional = window.VetEdgeProfessionalUI;
	if (typeof professional?.openRoute === "function") return professional.openRoute(route);
	const adapter = getRuntime()?.getAdapter?.("navigation:vetedge");
	if (adapter?.open?.(route) === true) return true;
	window.location.assign(deskRoute(route));
	return true;
}

function createDashboardComponent(page, config, runtime) {
	const EdgeAppShell = runtime.components.EdgeAppShell;
	const EdgePageLayout = runtime.components.EdgePageLayout;
	const EdgePageHeader = runtime.components.EdgePageHeader;
	const EdgeFilterBar = runtime.components.EdgeFilterBar;
	const EdgeLinkField = runtime.components.EdgeLinkField;
	const profile = currentProfile();
	const activeRoute = deskRoute(config.route || window.location.pathname || "");

	return {
		name: "VetEdgeSharedDashboardHost",
		data() {
			return {
				mountError: "",
				filters: initialFilters(),
				datePresets: datePresetOptions(),
				quickReports: [],
				reportsOpen: false,
				primaryAction: null,
				primaryActionLabel: __("Apply / Refresh"),
				_filterFields: {},
				_quickReportObserver: null,
			};
		},
		mounted() {
			try {
				if (!window.vetedgeDashboardShell?.mount) {
					throw new Error("The VetEdge dashboard renderer is unavailable.");
				}
				const host = this.$refs.dashboardHost;
				if (!host) throw new Error("The EdgeSuite dashboard host did not render.");
				window.vetedgeDashboardShell.mount(pageProxy(page, host, this), config);
				this.installQuickReportsBridge();
				window.EdgeSuiteNavigation?.syncActiveSection?.(
					host.closest?.(".edge-app-shell") || document.querySelector(".edge-app-shell"),
				);
			} catch (error) {
				console.error(`Unable to mount ${config.title || "VetEdge dashboard"}`, error);
				this.mountError = error?.message || String(error);
			}
		},
		beforeUnmount() {
			this._quickReportObserver?.disconnect?.();
			this._quickReportObserver = null;
		},
		methods: {
			searchBranches(term = "") {
				return new Promise((resolve, reject) => {
					frappe.call({
						method: BRANCH_SEARCH_API,
						args: {
							dashboard_key: config.key,
							txt: term || "",
							page_length: BRANCH_SEARCH_PAGE_LENGTH,
						},
						callback: (response) => resolve(response.message || []),
						error: reject,
					});
				});
			},
			setFilter(fieldname, value) {
				const field = this._filterFields[fieldname];
				if (field) return field.set_value(value);
				this.filters[fieldname] = value ?? "";
				return value;
			},
			applyFilters() {
				if (typeof this.primaryAction === "function") return this.primaryAction();
				return undefined;
			},
			syncQuickReports() {
				const host = this.$refs.dashboardHost;
				const linksHost = host?.querySelector?.(".vetedge-dashboard-links");
				if (!linksHost) return;
				this.quickReports = Array.from(linksHost.querySelectorAll(".vetedge-dashboard-report"))
					.map((button) => ({
						report: button.dataset.report || "",
						label: button.textContent?.trim?.() || button.dataset.report || "",
					}))
					.filter((item) => item.report);
				linksHost.hidden = true;
			},
			installQuickReportsBridge() {
				const host = this.$refs.dashboardHost;
				const linksHost = host?.querySelector?.(".vetedge-dashboard-links");
				if (!linksHost) return;
				this.syncQuickReports();
				this._quickReportObserver?.disconnect?.();
				if (window.MutationObserver) {
					this._quickReportObserver = new MutationObserver(() => this.syncQuickReports());
					this._quickReportObserver.observe(linksHost, { childList: true, subtree: true });
				}
			},
			openReport(report) {
				if (!report) return;
				this.reportsOpen = false;
				frappe.route_options = {
					branch: this.filters.branch || "",
					from_date: this.filters.from_date || "",
					to_date: this.filters.to_date || "",
					date_preset: this.filters.date_preset || "custom",
				};
				frappe.set_route("query-report", report);
			},
			renderFilters() {
				return h("div", { class: "vetedge-shared-dashboard-filter-grid" }, [
					h(EdgeLinkField, {
						modelValue: this.filters.branch,
						selectedLabel: this.filters.branch || __("All Branches"),
						label: __("Branch"),
						placeholder: __("Search branches"),
						searcher: this.searchBranches,
						clearable: true,
						"onUpdate:modelValue": (value) => this.setFilter("branch", value),
					}),
					h("div", { class: "edge-field" }, [
						h("label", { class: "edge-field-label" }, __("Period")),
						h(
							"select",
							{
								class: "edge-select edge-control",
								value: this.filters.date_preset,
								onChange: (event) => this.setFilter("date_preset", event.target.value),
							},
							this.datePresets.map((preset) =>
								h("option", { value: preset.value }, preset.label || preset.value),
							),
						),
					]),
					h("div", { class: "edge-field" }, [
						h("label", { class: "edge-field-label" }, __("From Date")),
						h("input", {
							class: "edge-input edge-control",
							type: "date",
							value: this.filters.from_date,
							disabled: this.filters.date_preset !== "custom",
							onChange: (event) => this.setFilter("from_date", event.target.value),
						}),
					]),
					h("div", { class: "edge-field" }, [
						h("label", { class: "edge-field-label" }, __("To Date")),
						h("input", {
							class: "edge-input edge-control",
							type: "date",
							value: this.filters.to_date,
							disabled: this.filters.date_preset !== "custom",
							onChange: (event) => this.setFilter("to_date", event.target.value),
						}),
					]),
				]);
			},
			renderFilterActions() {
				const actions = [
					h(
						"button",
						{
							class: "edge-button edge-button--primary edge-primary-button",
							type: "button",
							onClick: () => this.applyFilters(),
						},
						this.primaryActionLabel || __("Apply / Refresh"),
					),
				];
				if (this.quickReports.length) {
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
									this.quickReports.map((link) =>
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
				return actions;
			},
		},
		render() {
			const content = this.mountError
				? h("div", { class: "edge-error-state vetedge-dashboard-host-error" }, [
					h("strong", __("Dashboard failed to load")),
					h("p", this.mountError),
				])
				: h("div", {
					ref: "dashboardHost",
					class: "vetedge-dashboard-legacy-content",
					"data-dashboard-key": config.key || "",
				});

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
					default: () =>
						h(
							EdgePageLayout,
							{ class: "vetedge-shared-dashboard-page" },
							{
								header: () =>
									h(EdgePageHeader, {
										eyebrow: __("Veterinary Performance"),
										title: config.title || __("Veterinary Dashboard"),
										subtitle:
											config.subtitle ||
											__("Branch-aware veterinary operational and performance insights."),
									}),
								filters: () =>
									h(
										EdgeFilterBar,
										{ title: __("Dashboard Filters") },
										{
											default: () => this.renderFilters(),
											actions: () => this.renderFilterActions(),
										},
									),
								default: () => content,
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
				showFailure(
					page,
					professional?.message ||
						__("VetEdge requires the shared EdgeSuite professional shell."),
				);
				return;
			}

			frappe.require("/assets/vetedge/js/dashboard_shell.js", () => {
				try {
					loading.remove();
					$(page.body).empty();
					const root = $(
						'<div class="vetedge-shared-dashboard-root" data-edge-product="vetedge"></div>',
					).appendTo(page.body);
					const component = createDashboardComponent(page, config, runtime);
					wrapper.edge_dashboard_app?.unmount?.();
					wrapper.edge_dashboard_app = runtime.createEdgeApp(component);
					wrapper.edge_dashboard_view = wrapper.edge_dashboard_app.mount(root[0]);
				} catch (error) {
					console.error("Unable to mount shared VetEdge dashboard shell", error);
					showFailure(page, error?.message || String(error));
				}
			});
		};

		if (window.VetEdgeProfessionalUI?.install) {
			mountDashboard();
		} else {
			frappe.require("/assets/vetedge/js/vetedge_professional_ui.js", mountDashboard);
		}
	});

	return page;
}

export function mountVetEdgeDashboardHost(wrapper, config = {}) {
	if (!wrapper) throw new Error("A Frappe page wrapper is required.");
	return installDashboard(wrapper, config);
}

if (typeof window !== "undefined") {
	window.mountVetEdgeDashboardHost = mountVetEdgeDashboardHost;
}

export default mountVetEdgeDashboardHost;
