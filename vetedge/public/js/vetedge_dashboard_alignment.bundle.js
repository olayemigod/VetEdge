const ALIGNMENT_STYLE_ID = "vetedge-dashboard-alignment-style";
const ALIGNMENT_STYLE_URL = "/assets/vetedge/css/vetedge_dashboard_alignment.css?v=20260813-1";
const QUICK_REPORTS_ATTR = "data-vetedge-dashboard-bottom-reports";

const DASHBOARD_REPORTS = Object.freeze({
	"/desk/vetedge-clinical-dashboard": [
		"Consultation Register",
		"Planned Treatment",
		"Lab Order Report",
		"Vaccination Report",
	],
	"/desk/veterinary-financial-dashboard": [
		"Revenue Summary",
		"Unpaid Invoice Report",
		"Service Revenue Breakdown",
	],
	"/desk/vetedge-inventory-dispensary-dashboard": [
		"Dispensary Activity Report",
		"Stock Usage Summary",
	],
	"/desk/vetedge-lab-dashboard": ["Lab Order Report"],
	"/desk/vetedge-vaccination-dashboard": ["Vaccination Report"],
	"/desk/vetedge-boarding-dashboard": ["Boarding Report", "Kennel Availability Report"],
	"/desk/vetedge-grooming-dashboard": ["Grooming Report"],
	"/desk/vetedge-practitioner-performance-dashboard": [
		"Practitioner Performance Report",
		"Service Revenue Breakdown",
	],
	"/desk/vetedge-branch-performance-dashboard": [
		"Branch Performance Report",
		"Service Revenue Breakdown",
	],
});

let installed = false;
let scheduled = null;
let observer = null;

function ensureStyles() {
	if (document.getElementById(ALIGNMENT_STYLE_ID)) return;
	const link = document.createElement("link");
	link.id = ALIGNMENT_STYLE_ID;
	link.rel = "stylesheet";
	link.href = ALIGNMENT_STYLE_URL;
	document.head.appendChild(link);
}

function canonicalPath() {
	let path = String(window.location.pathname || "").replace(/\/+$/, "");
	if (path === "/app" || path.startsWith("/app/")) path = `/desk${path.slice(4)}`;
	return path || "/";
}

function currentReports() {
	return DASHBOARD_REPORTS[canonicalPath()] || [];
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

function createQuickReportsSection(reports) {
	const section = document.createElement("section");
	section.className = "vetedge-edge-dashboard-section vetedge-dashboard-bottom-reports";
	section.setAttribute(QUICK_REPORTS_ATTR, "1");

	const header = document.createElement("header");
	header.className = "vetedge-edge-dashboard-section__heading";
	const copy = document.createElement("div");
	const eyebrow = document.createElement("span");
	eyebrow.textContent = __("Reports");
	const title = document.createElement("h2");
	title.textContent = __("Quick Reports");
	const description = document.createElement("p");
	description.textContent = __("Open detailed reports using the dashboard's current Branch and date filters.");
	copy.append(eyebrow, title, description);
	header.appendChild(copy);
	section.appendChild(header);

	const links = document.createElement("div");
	links.className = "vetedge-dashboard-bottom-report-links";
	for (const reportName of reports) {
		const button = document.createElement("button");
		button.className = "edge-button edge-button--secondary edge-secondary-button";
		button.type = "button";
		button.textContent = __(reportName);
		button.addEventListener("click", () => openReport(reportName));
		links.appendChild(button);
	}
	section.appendChild(links);
	return section;
}

function alignRoot(root) {
	if (!root?.isConnected) return;
	const reports = currentReports();
	if (!reports.length) return;

	root.querySelectorAll(".vetedge-shared-dashboard-filter-actions .vetedge-dashboard-quick-reports").forEach((node) => {
		node.setAttribute("aria-hidden", "true");
	});

	const content = root.querySelector(".vetedge-edge-dashboard-content");
	if (!content) return;
	const existing = content.querySelector(`[${QUICK_REPORTS_ATTR}='1']`);
	if (existing) return;
	content.appendChild(createQuickReportsSection(reports));
}

function apply() {
	document.querySelectorAll(".vetedge-shared-dashboard-root").forEach(alignRoot);
}

function schedule() {
	window.clearTimeout(scheduled);
	scheduled = window.setTimeout(apply, 0);
}

function bindLifecycle() {
	if (observer || !window.MutationObserver || !document.body) return;
	observer = new MutationObserver((records) => {
		if (records.some((record) => record.addedNodes?.length || record.removedNodes?.length)) schedule();
	});
	observer.observe(document.body, { childList: true, subtree: true });
	window.frappe?.router?.on?.("change", schedule);
	for (const eventName of ["page-change", "desktop_screen"]) document.addEventListener(eventName, schedule);
}

function install() {
	ensureStyles();
	if (!installed) {
		bindLifecycle();
		installed = true;
	}
	schedule();
	return { installed: true, path: canonicalPath(), reports: currentReports().length };
}

if (typeof window !== "undefined") {
	window.VetEdgeDashboardAlignment = Object.assign(window.VetEdgeDashboardAlignment || {}, {
		install,
		apply,
		openReport,
	});
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", install, { once: true });
	else install();
}
