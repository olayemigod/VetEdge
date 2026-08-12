import { h } from "vue";

const HOST_STYLE_ID = "vetedge-shared-dashboard-host-style";
const HOST_STYLE_URL = "/assets/vetedge/css/vetedge_shared_dashboard_host.css?v=20260812-1";

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

function embeddedControl(parent, df) {
	if (!parent) throw new Error("The EdgeSuite dashboard filter host is unavailable.");
	if (!window.frappe?.ui?.form?.make_control) {
		throw new Error("Frappe control runtime is unavailable.");
	}

	const fieldHost = document.createElement("div");
	fieldHost.className = "vetedge-shared-dashboard-filter-field edge-field";
	parent.appendChild(fieldHost);

	const normalized = {
		...df,
		label: df.fieldname === "date_preset" ? __("Period") : df.label,
		change: df.change,
		onchange: df.change,
	};
	const control = window.frappe.ui.form.make_control({
		parent: fieldHost,
		df: normalized,
		render_input: true,
	});
	control.value = df.default == null ? "" : df.default;
	control.refresh?.();
	return control;
}

function pageProxy(page, body, filterFieldsHost, filterActionsHost) {
	const proxy = Object.create(page || null);
	proxy.body = body;
	proxy.edgeSuiteEmbedded = true;
	proxy.set_title = typeof page?.set_title === "function" ? page.set_title.bind(page) : () => {};
	proxy.add_field = (df) => embeddedControl(filterFieldsHost, df);
	proxy.set_primary_action = (label, action) => {
		if (!filterActionsHost) return null;
		let button = filterActionsHost.querySelector(".vetedge-shared-dashboard-refresh");
		if (!button) {
			button = document.createElement("button");
			button.type = "button";
			button.className =
				"edge-button edge-button--primary edge-primary-button vetedge-shared-dashboard-refresh";
			filterActionsHost.appendChild(button);
		}
		button.textContent = label || __("Apply / Refresh");
		button.onclick = (event) => {
			event.preventDefault();
			action?.();
		};
		return button;
	};
	proxy.clear_primary_action = () => {
		filterActionsHost?.querySelector(".vetedge-shared-dashboard-refresh")?.remove();
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
	const profile = currentProfile();
	const activeRoute = deskRoute(config.route || window.location.pathname || "");

	return {
		name: "VetEdgeSharedDashboardHost",
		data() {
			return { mountError: "" };
		},
		mounted() {
			try {
				if (!window.vetedgeDashboardShell?.mount) {
					throw new Error("The VetEdge dashboard renderer is unavailable.");
				}
				const host = this.$refs.dashboardHost;
				const filterFieldsHost = this.$refs.filterFieldsHost;
				const filterActionsHost = this.$refs.filterActionsHost;
				if (!host) throw new Error("The EdgeSuite dashboard host did not render.");
				if (!filterFieldsHost || !filterActionsHost) {
					throw new Error("The EdgeSuite dashboard filter bar did not render.");
				}
				window.vetedgeDashboardShell.mount(
					pageProxy(page, host, filterFieldsHost, filterActionsHost),
					config,
				);
				window.EdgeSuiteNavigation?.syncActiveSection?.(
					host.closest?.(".edge-app-shell") || document.querySelector(".edge-app-shell"),
				);
			} catch (error) {
				console.error(`Unable to mount ${config.title || "VetEdge dashboard"}`, error);
				this.mountError = error?.message || String(error);
			}
		},
		render() {
			const content = this.mountError
				? h("div", { class: "edge-error-state vetedge-dashboard-host-error" }, [
					h("strong", "Dashboard failed to load"),
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
					branchName: profile.branchName,
					userName: profile.userName,
					activeRoute,
					onNavigate: openRoute,
				},
				{
					default: () =>
						h(
							EdgePageLayout,
							null,
							{
								header: () =>
									h(EdgePageHeader, {
										eyebrow: "Veterinary Performance",
										title: config.title || "Veterinary Dashboard",
										subtitle:
											config.subtitle ||
											"Branch-aware veterinary operational and performance insights.",
									}),
								filters: () =>
									h(
										EdgeFilterBar,
										{ title: "Dashboard Filters" },
										{
											default: () =>
												h("div", {
													ref: "filterFieldsHost",
													class: "vetedge-shared-dashboard-filter-grid",
												}),
											actions: () =>
												h("div", {
													ref: "filterActionsHost",
													class: "vetedge-shared-dashboard-filter-actions",
												}),
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

	const requiredComponents = ["EdgeAppShell", "EdgePageLayout", "EdgePageHeader", "EdgeFilterBar"];
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