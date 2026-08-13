const ALIGNMENT_STYLE_ID = "vetedge-dashboard-parity-style";
const ALIGNMENT_STYLE_URL = "/assets/vetedge/css/vetedge_dashboard_parity.css?v=20260813-2";
const BOTTOM_REPORTS_ATTR = "data-vetedge-dashboard-bottom-reports";

const DASHBOARD_PATHS = new Set([
	"/desk/vetedge-executive-dashboard",
	"/desk/vetedge-clinical-dashboard",
	"/desk/veterinary-financial-dashboard",
	"/desk/vetedge-inventory-dispensary-dashboard",
	"/desk/vetedge-lab-dashboard",
	"/desk/vetedge-vaccination-dashboard",
	"/desk/vetedge-boarding-dashboard",
	"/desk/vetedge-grooming-dashboard",
	"/desk/vetedge-practitioner-performance-dashboard",
	"/desk/vetedge-branch-performance-dashboard",
]);

let installed = false;
let scheduled = null;
let observer = null;
let dashboardClickBound = false;
let adapterPatched = false;

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
	for (const fieldname of ["from_date", "to_date", "branch"]) {
		const value = source[fieldname];
		if (value !== undefined && value !== null && String(value) !== "") result[fieldname] = value;
	}
	return result;
}

function openReport(reportName) {
	if (!reportName || typeof window.frappe?.set_route !== "function") return false;
	window.frappe.route_options = reportFilters();
	window.frappe.set_route("query-report", reportName);
	return true;
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
	}, 0);
}

function bindDashboardClicks() {
	if (dashboardClickBound) return;
	dashboardClickBound = true;
	document.addEventListener(
		"click",
		(event) => {
			if (event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
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
			if (isDashboardRoute(route)) return navigateSameTab(route);
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
	if (!installed) {
		bindLifecycle();
		installed = true;
	}
	if (window.frappe?.require) {
		window.frappe.require("edgeui.bundle.js", () => {
			patchNavigationAdapter();
			schedule();
		});
	} else {
		schedule();
	}
	window.setTimeout(schedule, 80);
	window.setTimeout(schedule, 250);
	return { installed: true, adapterPatched, dashboardCount: DASHBOARD_PATHS.size };
}

if (typeof window !== "undefined") {
	window.VetEdgeDashboardAlignment = Object.assign(window.VetEdgeDashboardAlignment || {}, {
		install,
		apply,
		openReport,
		navigateSameTab,
	});
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install, { once: true });
	else install();
}
