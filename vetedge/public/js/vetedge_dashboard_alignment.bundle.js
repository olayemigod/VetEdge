import { h } from "vue";

const ALIGNMENT_STYLE_ID = "vetedge-dashboard-parity-style";
const ALIGNMENT_STYLE_URL = "/assets/vetedge/css/vetedge_dashboard_parity.css?v=20260817-1";
const BOTTOM_REPORTS_ATTR = "data-vetedge-dashboard-bottom-reports";
const REPORT_CENTER_PATH = "/desk/vetedge-report-center";
const CAPABILITIES_API = "vetedge.services.reporting_capabilities.get_shell_capabilities";
const DASHBOARD_EXPORT_API = "/api/method/vetedge.services.dashboard_reporting_actions.download_dashboard";
const DASHBOARD_PRINT_API = "vetedge.services.dashboard_reporting_actions.get_dashboard_print_html";

const DASHBOARD_ROUTE_KEYS = new Map([
	["/desk/vetedge-executive-dashboard", "executive"],
	["/desk/vetedge-clinical-dashboard", "clinical"],
	["/desk/veterinary-financial-dashboard", "financial"],
	["/desk/vetedge-inventory-dispensary-dashboard", "inventory_dispensary"],
	["/desk/vetedge-lab-dashboard", "lab"],
	["/desk/vetedge-vaccination-dashboard", "vaccination"],
	["/desk/vetedge-hospitalisation-dashboard", "hospitalisation"],
	["/desk/vetedge-boarding-dashboard", "boarding"],
	["/desk/vetedge-grooming-dashboard", "grooming"],
	["/desk/vetedge-practitioner-performance-dashboard", "practitioner_performance"],
	["/desk/vetedge-branch-performance-dashboard", "branch_performance"],
]);
const DASHBOARD_PATHS = new Set(DASHBOARD_ROUTE_KEYS.keys());

let installed = false;
let scheduled = null;
let observer = null;
let dashboardClickBound = false;
let adapterPatched = false;
let dashboardShellPatched = false;

function ensureStyles() {
	if (document.getElementById(ALIGNMENT_STYLE_ID)) return;
	const link = document.createElement("link");
	link.id = ALIGNMENT_STYLE_ID;
	link.rel = "stylesheet";
	link.href = ALIGNMENT_STYLE_URL;
	document.head.appendChild(link);
}

function canonicalTarget(route) {
	const raw = String(route || "").trim();
	if (!raw) return "";
	try {
		const url = new URL(raw, window.location.origin);
		if (url.origin !== window.location.origin) return raw;
		if (url.pathname === "/app" || url.pathname.startsWith("/app/")) {
			url.pathname = `/desk${url.pathname.slice(4)}`;
		}
		return `${url.pathname}${url.search}${url.hash}`;
	} catch (_error) {
		return raw.replace(/^\/app(?=\/|$)/, "/desk");
	}
}

function canonicalPath(route) {
	try {
		return new URL(canonicalTarget(route), window.location.origin).pathname.replace(/\/+$/, "") || "/";
	} catch (_error) {
		return String(route || "").split("?")[0].replace(/\/+$/, "") || "/";
	}
}

function dashboardKey(route = window.location.pathname) {
	return DASHBOARD_ROUTE_KEYS.get(canonicalPath(route)) || "";
}

function isDashboardRoute(route) {
	return DASHBOARD_PATHS.has(canonicalPath(route));
}

function navigateSameTab(route) {
	const target = canonicalTarget(route);
	if (!target) return false;
	if (window.VetEdgeNavigationRecovery?.navigate?.(target) === true) return true;

	try {
		const url = new URL(target, window.location.origin);
		if (url.origin !== window.location.origin || !url.pathname.startsWith("/desk")) {
			window.location.assign(target);
			return true;
		}
		if (typeof window.frappe?.set_route !== "function") {
			window.location.assign(target);
			return true;
		}
		window.frappe.route_options = {};
		for (const [key, value] of url.searchParams) window.frappe.route_options[key] = value;
		const parts = url.pathname
			.replace(/^\/desk(?:\/|$)/, "")
			.split("/")
			.filter(Boolean)
			.map(decodeURIComponent);
		if (!parts.length) return false;
		window.frappe.set_route(...parts);
		return true;
	} catch (_error) {
		window.location.assign(target);
		return true;
	}
}

function reportFilters() {
	const source = window.frappe?.route_options || {};
	const result = {};
	for (const fieldname of ["from_date", "to_date", "branch", "date_preset", "customer", "practitioner", "service_category", "item"]) {
		const value = source[fieldname];
		if (value !== undefined && value !== null && String(value) !== "") result[fieldname] = value;
	}
	return result;
}

function reportCenterTarget(reportName, extraFilters = {}) {
	const report = String(reportName || "").trim();
	if (!report) return "";
	const source = canonicalPath(window.location.pathname) || "/desk/vetedge-executive-dashboard";
	const params = new URLSearchParams({ report, source });
	const filters = { ...reportFilters(), ...(extraFilters || {}) };
	for (const [key, value] of Object.entries(filters)) {
		if (value !== undefined && value !== null && String(value) !== "") params.set(key, String(value));
	}
	return `${REPORT_CENTER_PATH}?${params.toString()}`;
}

function openReport(reportName, extraFilters = {}) {
	const target = reportCenterTarget(reportName, extraFilters);
	if (!target) return false;
	return navigateSameTab(target);
}

function apiCall(method, args = {}) {
	return new Promise((resolve, reject) => {
		window.frappe.call({
			method,
			args,
			callback: (response) => resolve(response.message || {}),
			error: reject,
		});
	});
}

function exportRuntime() {
	return window.EdgeSuiteReportExport || window.EdgeSuiteUI?.reportExport || window.EdgeUI?.reportExport || null;
}

function printRuntime() {
	return window.EdgeSuiteReportPrint || window.EdgeSuiteUI?.reportPrint || window.EdgeUI?.reportPrint || null;
}

function serverErrorMessage(xhr) {
	try {
		const text = new TextDecoder("utf-8").decode(new Uint8Array(xhr.response || []));
		const parsed = JSON.parse(text);
		return parsed?.message || parsed?.exc || parsed?._server_messages || "";
	} catch (_error) {
		return "";
	}
}

function responseFilename(xhr, key, format) {
	const disposition = xhr.getResponseHeader("Content-Disposition") || "";
	const match = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
	if (match?.[1]) {
		try {
			return decodeURIComponent(match[1].replace(/^\"|\"$/g, ""));
		} catch (_error) {
			return match[1].replace(/^\"|\"$/g, "");
		}
	}
	return `VetEdge-${key || "dashboard"}.${format || "xlsx"}`;
}

function downloadDashboard(key, filters, options = {}) {
	return new Promise((resolve, reject) => {
		const exports = exportRuntime();
		if (!exports?.normalizeOptions || !exports?.downloadVerified) {
			reject(new Error(__("The shared EdgeSuite export runtime is unavailable.")));
			return;
		}
		const normalized = exports.normalizeOptions({ ...(options || {}), artifact_kind: "dashboard" });
		const formData = new FormData();
		formData.append("dashboard_key", key);
		formData.append("filters", JSON.stringify(filters || {}));
		formData.append("options", JSON.stringify(normalized));
		const xhr = new XMLHttpRequest();
		xhr.open("POST", DASHBOARD_EXPORT_API);
		xhr.responseType = "arraybuffer";
		xhr.setRequestHeader("X-Frappe-CSRF-Token", window.frappe.csrf_token);
		xhr.onload = () => {
			if (xhr.status < 200 || xhr.status >= 300) {
				reject(new Error(serverErrorMessage(xhr) || `Dashboard export failed with HTTP ${xhr.status}.`));
				return;
			}
			try {
				const bytes = new Uint8Array(xhr.response || []);
				const mime = xhr.getResponseHeader("Content-Type") || exports.expectedMime(normalized.format);
				const filename = responseFilename(xhr, key, normalized.format);
				exports.downloadVerified({ bytes, format: normalized.format, mime, filename });
				resolve({ filename, format: normalized.format });
			} catch (error) {
				reject(error);
			}
		};
		xhr.onerror = () => reject(new Error(__("Dashboard export request failed. Please check the connection and try again.")));
		xhr.send(formData);
	});
}

function printDashboard(key, filters) {
	return new Promise((resolve, reject) => {
		const prints = printRuntime();
		const exports = exportRuntime();
		if (!prints?.open || !exports?.normalizeOptions) {
			reject(new Error(__("The shared EdgeSuite print runtime is unavailable.")));
			return;
		}
		const printWindow = window.open?.("", "_blank");
		if (!printWindow) {
			reject(new Error(__("The print window could not be opened. Please allow pop-ups and try again.")));
			return;
		}
		const options = exports.normalizeOptions({
			format: "pdf",
			scope: "all_filtered",
			include_title: true,
			include_filters: true,
			include_summary: true,
			include_charts: true,
			include_generated_metadata: true,
			repeat_table_headings: true,
		});
		window.frappe.call({
			method: DASHBOARD_PRINT_API,
			args: { dashboard_key: key, filters: JSON.stringify(filters || {}), options: JSON.stringify(options) },
			callback: (response) => {
				try {
					prints.open({ html: response.message || "", title: key || "Dashboard", printWindow });
					resolve(true);
				} catch (error) {
					printWindow.close?.();
					reject(error);
				}
			},
			error: (error) => {
				printWindow.close?.();
				reject(error instanceof Error ? error : new Error(__("Dashboard print generation failed.")));
			},
		});
	});
}

function dashboardShellLayoutAdapter(BasePageLayout, EdgeDashboardShell) {
	return {
		name: "VetEdgeDashboardShellLayoutAdapter",
		inheritAttrs: false,
		data() {
			return {
				capabilities: { can_view: true, can_print: false, can_export: false },
				exportBusy: false,
				printBusy: false,
			};
		},
		mounted() {
			this.loadCapabilities();
		},
		methods: {
			async loadCapabilities() {
				const key = dashboardKey();
				if (!key) return;
				try {
					this.capabilities = await apiCall(CAPABILITIES_API, { scope_name: key, scope_type: "dashboard" });
				} catch (error) {
					console.warn("VetEdge dashboard action capabilities could not be loaded", error);
					this.capabilities = { can_view: true, can_print: false, can_export: false };
				}
			},
			async handleExport(options) {
				const key = dashboardKey();
				if (!key || !this.capabilities.can_export) return;
				this.exportBusy = true;
				try {
					await downloadDashboard(key, reportFilters(), options || {});
				} catch (error) {
					window.frappe.msgprint({ title: __("Dashboard Export Failed"), message: error?.message || String(error), indicator: "red" });
				} finally {
					this.exportBusy = false;
				}
			},
			async handlePrint() {
				const key = dashboardKey();
				if (!key || !this.capabilities.can_print) return;
				this.printBusy = true;
				try {
					await printDashboard(key, reportFilters());
				} catch (error) {
					window.frappe.msgprint({ title: __("Dashboard Print Failed"), message: error?.message || String(error), indicator: "red" });
				} finally {
					this.printBusy = false;
				}
			},
		},
		render() {
			const key = dashboardKey();
			if (!key) return h(BasePageLayout, this.$attrs, this.$slots);

			const headerVNode = this.$slots.header?.()?.[0] || null;
			const headerProps = headerVNode?.props || {};
			const filterVNode = this.$slots.filters?.()?.[0] || null;
			const filterSlots = filterVNode?.children && typeof filterVNode.children === "object" ? filterVNode.children : {};
			const filtersSlot = typeof filterSlots.default === "function" ? filterSlots.default : undefined;
			const filterActionsSlot = typeof filterSlots.actions === "function" ? filterSlots.actions : undefined;

			return h(
				EdgeDashboardShell,
				{
					...this.$attrs,
					title: headerProps.title || __("Veterinary Dashboard"),
					eyebrow: headerProps.eyebrow || __("Veterinary Performance"),
					subtitle: headerProps.subtitle || __("Branch-aware veterinary operational and performance insights."),
					exportEnabled: Boolean(this.capabilities.can_export),
					printEnabled: Boolean(this.capabilities.can_print),
					exportBusy: this.exportBusy,
					printBusy: this.printBusy,
					onExport: this.handleExport,
					onPrint: this.handlePrint,
				},
				{
					filters: filtersSlot,
					filterActions: filterActionsSlot,
					default: () => this.$slots.default?.() || [],
				},
			);
		},
	};
}

function installDashboardShellAdapter() {
	const edgeUI = window.EdgeSuiteUI || window.EdgeUI;
	const components = edgeUI?.components || edgeUI;
	if (!components?.EdgePageLayout || !components?.EdgeDashboardShell) return false;
	if (components.EdgePageLayout?.__vetedgeDashboardShellAdapter) {
		dashboardShellPatched = true;
		return true;
	}
	const BasePageLayout = components.EdgePageLayout;
	const adapter = dashboardShellLayoutAdapter(BasePageLayout, components.EdgeDashboardShell);
	adapter.__vetedgeDashboardShellAdapter = true;
	try {
		components.EdgePageLayout = adapter;
		dashboardShellPatched = components.EdgePageLayout === adapter;
	} catch (error) {
		console.warn("VetEdge could not install the EdgeDashboardShell compatibility adapter", error);
		dashboardShellPatched = false;
	}
	return dashboardShellPatched;
}

function quickReportButton(event) {
	const target = event.target;
	if (!target?.closest) return null;
	return target.closest(
		".vetedge-dashboard-quick-report-item, .vetedge-executive-report-actions .edge-button",
	);
}

function alignRoot(root) {
	if (!root?.isConnected) return;
	root.classList.add("vetedge-dashboard-parity-ready");
	root.querySelectorAll(`[${BOTTOM_REPORTS_ATTR}='1']`).forEach((node) => node.remove());
	root.querySelectorAll(".vetedge-shared-dashboard-filter-actions .vetedge-dashboard-quick-reports").forEach((node) => {
		node.removeAttribute("aria-hidden");
	});
}

function apply() {
	document.querySelectorAll(".vetedge-shared-dashboard-root").forEach(alignRoot);
}

function schedule() {
	window.clearTimeout(scheduled);
	scheduled = window.setTimeout(() => {
		apply();
		patchNavigationAdapter();
		installDashboardShellAdapter();
	}, 0);
}

function bindDashboardClicks() {
	if (dashboardClickBound) return;
	dashboardClickBound = true;
	document.addEventListener(
		"click",
		(event) => {
			if (event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

			const reportButton = quickReportButton(event);
			if (reportButton) {
				const reportName = String(reportButton.textContent || "").replace(/\s+/g, " ").trim();
				if (reportName) {
					event.preventDefault();
					event.stopImmediatePropagation();
					openReport(reportName);
					return;
				}
			}

			const anchor = event.target?.closest?.("a[href]");
			if (!anchor || !isDashboardRoute(anchor.href)) return;
			event.preventDefault();
			event.stopPropagation();
			navigateSameTab(anchor.href);
		},
		true,
	);
}

function patchNavigationAdapter() {
	const edgeUI = window.EdgeSuiteUI || window.EdgeUI;
	if (!edgeUI?.getAdapter || !edgeUI?.registerAdapter) return false;
	const current = edgeUI.getAdapter("navigation:vetedge") || edgeUI.getAdapter("navigation:veterinary");
	if (!current) return false;
	if (current.__vetedgeDashboardSameTab) {
		adapterPatched = true;
		return true;
	}
	const wrapped = {
		...current,
		__vetedgeDashboardSameTab: true,
		open(route) {
			if (isDashboardRoute(route) || canonicalPath(route) === REPORT_CENTER_PATH) return navigateSameTab(route);
			return current.open?.(route) ?? false;
		},
	};
	edgeUI.registerAdapter("navigation:vetedge", wrapped, { replace: true });
	edgeUI.registerAdapter("navigation:veterinary", wrapped, { replace: true });
	adapterPatched = true;
	return true;
}

function bindLifecycle() {
	if (observer || !window.MutationObserver || !document.body) return;
	observer = new MutationObserver((records) => {
		if (records.some((record) => record.addedNodes?.length || record.removedNodes?.length)) schedule();
	});
	observer.observe(document.body, { childList: true, subtree: true });
	window.frappe?.router?.on?.("change", schedule);
	for (const eventName of ["page-change", "desktop_screen", "sidebar_setup", "toolbar_setup"]) {
		document.addEventListener(eventName, schedule);
	}
}

function install() {
	ensureStyles();
	bindDashboardClicks();
	installDashboardShellAdapter();
	if (!installed) {
		bindLifecycle();
		installed = true;
	}
	if (window.frappe?.require) {
		window.frappe.require("edgeui.bundle.js", () => {
			patchNavigationAdapter();
			installDashboardShellAdapter();
			schedule();
		});
	} else {
		schedule();
	}
	window.setTimeout(schedule, 80);
	window.setTimeout(schedule, 250);
	return { installed: true, adapterPatched, dashboardShellPatched, dashboardCount: DASHBOARD_PATHS.size };
}

if (typeof window !== "undefined") {
	window.VetEdgeDashboardAlignment = Object.assign(window.VetEdgeDashboardAlignment || {}, {
		install,
		apply,
		openReport,
		reportCenterTarget,
		navigateSameTab,
		dashboardKey,
		downloadDashboard,
		printDashboard,
	});
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install, { once: true });
	else install();
}
