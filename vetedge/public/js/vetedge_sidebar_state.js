// VetEdge sidebar focus bridge for EdgeSuite Navigation Shell V2.
//
// EdgeSuite owns presentation, theme colouring, rail collapse and accordion
// behaviour. VetEdge supplies product-specific route context for pages that host
// several logical resources on one Frappe Page route (for example Resource
// Center). This keeps the active section/submenu accurate without duplicating
// EdgeSuite navigation styling in the product app.
(function () {
	"use strict";

	if (typeof window === "undefined" || typeof document === "undefined") return;

	const SHELL_SELECTOR = ".edge-app-shell[data-edge-product='vetedge'], .edge-app-shell[data-edge-product='veterinary']";
	const ITEM_SELECTOR = ".edge-sidebar-item";
	const LABEL_SELECTOR = ".edge-sidebar-item__label";
	const SECTION_SELECTOR = ".edge-sidebar__section";
	const SECTION_TOGGLE_SELECTOR = ".edge-sidebar__section-toggle";
	let observer = null;
	let scheduled = false;

	const RESOURCE_LABELS = Object.freeze({
		patients: ["Patients"],
		appointments: ["Appointments"],
		"missed-appointments": ["Missed Appointments"],
		consultations: ["Consultations"],
		"lab-orders": ["Lab Orders", "Laboratory Orders"],
		vaccinations: ["Vaccinations", "Vaccination Records"],
		grooming: ["Grooming Appointments"],
		boarding: ["Boarding Bookings"],
		kennels: ["Kennels", "Kennels and Care Locations"],
	});

	const MASTER_LABELS = Object.freeze({
		species: ["Species"],
		breeds: ["Breeds"],
		symptoms: ["Symptoms"],
		"diagnosis-categories": ["Diagnosis Categories"],
		diagnoses: ["Diagnoses"],
		"service-types": ["Service Types"],
		"consultation-types": ["Consultation Types"],
	});

	const PRICING_LABELS = Object.freeze({
		"treatment-items": ["Treatment Items"],
		"treatment-types": ["Treatment Types"],
		"lab-tests": ["Lab Tests"],
		vaccines: ["Vaccines"],
		"grooming-services": ["Grooming Services"],
	});

	const SERVICE_LABELS = Object.freeze({
		availability: ["Kennel Availability", "Availability"],
		"boarding-stays": ["Boarding Stays"],
		"boarding-care-records": ["Boarding Care Records"],
		"grooming-sessions": ["Grooming Sessions"],
	});

	function path() {
		return String(window.location.pathname || "").replace(/\/+$/, "");
	}

	function query() {
		return new URLSearchParams(window.location.search || "");
	}

	function focusLabels() {
		const currentPath = path();
		const params = query();

		if (currentPath === "/desk/vetedge-resource-center") {
			return RESOURCE_LABELS[params.get("resource") || "patients"] || ["Patients"];
		}
		if (currentPath === "/desk/vetedge-master-workspace") {
			return MASTER_LABELS[params.get("resource") || ""] || [];
		}
		if (currentPath === "/desk/vetedge-pricing-master-workspace") {
			return PRICING_LABELS[params.get("resource") || ""] || [];
		}
		if (currentPath === "/desk/vetedge-service-operations") {
			return SERVICE_LABELS[params.get("resource") || ""] || [];
		}
		if (currentPath === "/desk/vetedge-front-desk-action-center") {
			const tab = params.get("tab") || "queue";
			if (tab === "guest") return ["Guest Booking Requests"];
			if (tab === "missed") return ["Missed Appointments"];
			return ["Appointment Queue"];
		}
		if (currentPath === "/desk/vetedge-clinical-workspace") return ["Consultations"];
		if (currentPath === "/desk/veterinary-medical-history") return ["Medical History"];
		if (currentPath === "/desk/veterinary-settings-center") return ["Veterinary Settings", "Settings"];
		if (currentPath === "/desk/vetedge") return ["Veterinary Home"];
		return [];
	}

	function labelFor(item) {
		return String(item?.querySelector?.(LABEL_SELECTOR)?.textContent || "").trim();
	}

	function itemForLabels(shell, labels) {
		const wanted = new Set((labels || []).map((label) => String(label).trim()).filter(Boolean));
		if (!wanted.size) return null;
		return [...shell.querySelectorAll(ITEM_SELECTOR)].find((item) => wanted.has(labelFor(item))) || null;
	}

	function collapseOtherSections(shell, activeSection) {
		shell.querySelectorAll(SECTION_TOGGLE_SELECTOR).forEach((toggle) => {
			const section = toggle.closest(SECTION_SELECTOR);
			if (!section || section === activeSection) return;
			if (toggle.getAttribute("aria-expanded") === "true") toggle.click();
		});
	}

	function syncShell(shell) {
		const labels = focusLabels();
		if (!labels.length) {
			window.EdgeSuiteNavigation?.syncActiveSection?.(shell);
			return;
		}

		const activeItem = itemForLabels(shell, labels);
		if (!activeItem) return;

		shell.querySelectorAll(ITEM_SELECTOR).forEach((item) => {
			const isActive = item === activeItem;
			item.classList.toggle("active", isActive);
			if (isActive) item.setAttribute("aria-current", "page");
			else item.removeAttribute("aria-current");
		});

		const activeSection = activeItem.closest(SECTION_SELECTOR);
		const activeToggle = activeSection?.querySelector?.(SECTION_TOGGLE_SELECTOR);
		if (activeToggle && activeToggle.getAttribute("aria-expanded") !== "true") {
			activeToggle.click();
		}

		window.setTimeout(() => {
			collapseOtherSections(shell, activeSection);
			window.EdgeSuiteNavigation?.syncActiveSection?.(shell);
		}, 0);
	}

	function sync() {
		document.querySelectorAll(SHELL_SELECTOR).forEach(syncShell);
	}

	function schedule() {
		if (scheduled) return;
		scheduled = true;
		window.setTimeout(() => {
			scheduled = false;
			sync();
		}, 0);
	}

	function patchHistoryMethod(name) {
		const history = window.history;
		const original = history?.[name];
		if (typeof original !== "function" || original.__vetedgeSidebarFocusPatched) return;
		const wrapped = function (...args) {
			const result = original.apply(this, args);
			schedule();
			return result;
		};
		wrapped.__vetedgeSidebarFocusPatched = true;
		history[name] = wrapped;
	}

	function startObserver() {
		if (observer || !document.body || !window.MutationObserver) return;
		observer = new MutationObserver((records) => {
			if (
				records.some((record) =>
					[...(record.addedNodes || [])].some(
						(node) => node.nodeType === 1 && (node.matches?.(SHELL_SELECTOR) || node.querySelector?.(SHELL_SELECTOR)),
					),
				)
			) {
				schedule();
			}
		});
		observer.observe(document.body, { childList: true, subtree: true });
	}

	function install() {
		patchHistoryMethod("pushState");
		patchHistoryMethod("replaceState");
		startObserver();
		schedule();
		window.setTimeout(sync, 60);
		window.setTimeout(sync, 250);
	}

	for (const eventName of ["page-change", "desktop_screen", "sidebar_setup", "toolbar_setup"]) {
		document.addEventListener(eventName, schedule);
	}
	window.addEventListener("popstate", schedule);

	window.VetEdgeSidebarState = Object.assign(window.VetEdgeSidebarState || {}, {
		install,
		sync,
		focusLabels,
	});

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", install, { once: true });
	} else {
		install();
	}
})();
