// VetEdge EdgeSuite UI adapter for native Frappe Desk list, form, workflow, dialog, and settings screens.
// This layer is presentation-only. Frappe controllers and VetEdge services remain the source of business truth.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const ASSET_VERSION = "20260722-1";
	const ROOT_CLASSES = [
		"vetedge-edge-desk",
		"vetedge-edge-list",
		"vetedge-edge-form",
		"vetedge-edge-settings",
	];
	const ROUTE_EVENTS = ["page-change", "form-refresh", "list-rendered"];
	const NATIVE_ROUTE_PREFIXES = [
		"/app/veterinary-",
		"/app/pet-",
		"/app/kennel",
		"/app/consultation-",
		"/app/lab-",
	];
	const SCREEN_COPY = Object.freeze({
		"Veterinary Patient": {
			eyebrow: "Patient Management",
			subtitle: "Maintain complete, branch-aware veterinary patient records.",
		},
		"Veterinary Appointment": {
			eyebrow: "Front Desk",
			subtitle: "Schedule appointments and move each visit through the correct workflow.",
		},
		"Veterinary Missed Appointment": {
			eyebrow: "Front Desk",
			subtitle: "Review missed visits and complete the approved follow-up action.",
		},
		"Veterinary Consultation": {
			eyebrow: "Clinical Workflow",
			subtitle: "Document assessment, diagnosis, treatment, billing, and clinical progress safely.",
		},
		"Veterinary Lab Order": {
			eyebrow: "Laboratory",
			subtitle: "Manage test requests, results, billing, and review status.",
		},
		"Veterinary Vaccination Record": {
			eyebrow: "Preventive Care",
			subtitle: "Record vaccinations, due dates, stock use, and payment status.",
		},
		"Veterinary Hospitalisation": {
			eyebrow: "In-patient Care",
			subtitle: "Coordinate admission, care activities, charges, readiness, and discharge.",
		},
		"Pet Grooming Appointment": {
			eyebrow: "Grooming",
			subtitle: "Plan grooming visits with branch, patient, service, and billing context.",
		},
		"Pet Grooming Session": {
			eyebrow: "Grooming",
			subtitle: "Complete the grooming service workflow and related billing actions.",
		},
		"Pet Boarding Booking": {
			eyebrow: "Boarding",
			subtitle: "Manage reservations, care requirements, admission, and billing preparation.",
		},
		"Pet Boarding Stay": {
			eyebrow: "Boarding",
			subtitle: "Track active stays, assigned care locations, charges, and release status.",
		},
		"Veterinary Settings": {
			eyebrow: "Veterinary Configuration",
			subtitle: "Control clinical, billing, notification, inventory, and workflow behaviour.",
		},
	});

	const state = {
		installed: false,
		observer: null,
		scheduled: null,
		lastContext: null,
		lastError: null,
		navigationPatched: false,
	};

	function runtime() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	}

	function normalizePath(route) {
		const raw = String(route || "").trim();
		if (!raw) return "";
		try {
			const url = new URL(raw, window.location.origin);
			return url.pathname.replace(/\/$/, "") || "/";
		} catch (_error) {
			return raw.split("?")[0].replace(/\/$/, "");
		}
	}

	function isNativeVetEdgePath(path) {
		const normalized = normalizePath(path);
		return NATIVE_ROUTE_PREFIXES.some((prefix) => normalized === prefix || normalized.startsWith(prefix));
	}

	function patchNavigationAdapter() {
		const edgeUI = runtime();
		if (!edgeUI?.registerAdapter || state.navigationPatched) return false;

		const existing = edgeUI.getAdapter?.("navigation:vetedge") || null;
		const adapter = {
			open(route) {
				const path = normalizePath(route);
				if (isNativeVetEdgePath(path)) {
					window.location.assign(route);
					return true;
				}
				if (existing?.open) return existing.open(route) === true;
				return false;
			},
		};

		edgeUI.registerAdapter("navigation:vetedge", adapter, { replace: true });
		edgeUI.registerAdapter("navigation:veterinary", adapter, { replace: true });
		state.navigationPatched = true;
		return true;
	}

	function currentRoute() {
		try {
			return window.frappe?.get_route?.() || [];
		} catch (_error) {
			return [];
		}
	}

	function currentContext() {
		const route = currentRoute();
		const view = String(route[0] || "");
		const doctype = String(route[1] || "");
		if (!doctype || !["List", "Form"].includes(view)) return null;

		let meta = null;
		try {
			meta = window.frappe?.get_meta?.(doctype) || null;
		} catch (_error) {
			return null;
		}
		if (!meta || String(meta.module || "") !== "Veterinary") return null;

		const isSettings = Boolean(meta.issingle || doctype === "Veterinary Settings");
		return {
			route,
			view,
			doctype,
			name: String(route[2] || ""),
			meta,
			kind: isSettings ? "settings" : view === "List" ? "list" : "form",
		};
	}

	function visiblePage() {
		const pages = Array.from(document.querySelectorAll(".page-container"));
		return pages.find((page) => page.offsetParent !== null && !page.classList.contains("hide")) || pages.at(-1) || null;
	}

	function copyFor(context) {
		const configured = SCREEN_COPY[context.doctype] || {};
		if (configured.eyebrow || configured.subtitle) return configured;
		const isSettings = context.kind === "settings";
		return {
			eyebrow: isSettings ? "Veterinary Configuration" : context.kind === "list" ? "Veterinary Records" : "Veterinary Workflow",
			subtitle: isSettings
				? "Configure this Veterinary feature using the permitted settings below."
				: context.kind === "list"
					? "Search, filter, and open the records you are permitted to access."
					: "Complete the record using the approved Veterinary workflow and actions.",
		};
	}

	function clearBodyContext() {
		ROOT_CLASSES.forEach((className) => document.body?.classList.remove(className));
		if (document.body) {
			delete document.body.dataset.vetedgeDoctype;
			delete document.body.dataset.vetedgeView;
		}
	}

	function applyBodyContext(context) {
		clearBodyContext();
		document.body?.classList.add("edge-suite-product-vetedge", "vetedge-edge-desk", `vetedge-edge-${context.kind}`);
		if (document.body) {
			document.body.dataset.vetedgeDoctype = context.doctype;
			document.body.dataset.vetedgeView = context.kind;
		}
	}

	function mark(node, className, role) {
		if (!node) return;
		node.classList.add(className);
		if (role) node.dataset.edgeRole = role;
	}

	function enhanceHeader(page, context) {
		const head = page.querySelector(".page-head") || document.querySelector(".page-head");
		if (!head) return;
		mark(head, "vetedge-edge-page-head", "page-header");

		const titleArea = head.querySelector(".page-title") || head.querySelector(".title-area");
		if (!titleArea) return;
		mark(titleArea, "vetedge-edge-title-area");
		const copy = copyFor(context);

		let eyebrow = titleArea.querySelector(".vetedge-edge-eyebrow");
		if (!eyebrow) {
			eyebrow = document.createElement("div");
			eyebrow.className = "vetedge-edge-eyebrow";
			titleArea.prepend(eyebrow);
		}
		eyebrow.textContent = copy.eyebrow;

		let subtitle = titleArea.querySelector(".vetedge-edge-subtitle");
		if (!subtitle) {
			subtitle = document.createElement("div");
			subtitle.className = "vetedge-edge-subtitle";
			titleArea.append(subtitle);
		}
		subtitle.textContent = copy.subtitle;

		head.querySelectorAll(".primary-action, .btn-primary").forEach((button) => mark(button, "vetedge-edge-primary-action", "primary-action"));
		head.querySelectorAll(".actions-btn-group, .menu-btn-group").forEach((group) => mark(group, "vetedge-edge-action-menu", "action-menu"));
	}

	function enhanceList(page) {
		mark(page.querySelector(".layout-main-section"), "vetedge-edge-surface", "list-surface");
		page.querySelectorAll(".list-view, .list-view-container").forEach((node) => mark(node, "vetedge-edge-list-view"));
		page.querySelectorAll(".list-row-head").forEach((node) => mark(node, "vetedge-edge-list-head"));
		page.querySelectorAll(".list-row-container").forEach((node) => mark(node, "vetedge-edge-list-row"));
		page.querySelectorAll(".list-filters, .filter-section, .list-view-actions").forEach((node) => mark(node, "vetedge-edge-filter-area", "filters"));
		page.querySelectorAll(".list-paging-area, .list-paging-area .btn-group").forEach((node) => mark(node, "vetedge-edge-pagination", "pagination"));
		page.querySelectorAll(".indicator-pill, .list-row .indicator, .status").forEach((node) => mark(node, "vetedge-edge-status", "status"));
		page.querySelectorAll(".list-empty-state, .no-result").forEach((node) => mark(node, "vetedge-edge-empty-state", "empty-state"));
		page.querySelectorAll(".list-sidebar").forEach((node) => mark(node, "vetedge-edge-list-sidebar", "list-sidebar"));
	}

	function enhanceForm(page, context) {
		mark(page.querySelector(".layout-main-section"), "vetedge-edge-surface", "form-surface");
		page.querySelectorAll(".form-layout, .form-page").forEach((node) => mark(node, "vetedge-edge-form-layout"));
		page.querySelectorAll(".form-dashboard").forEach((node) => mark(node, "vetedge-edge-form-dashboard", "form-dashboard"));
		page.querySelectorAll(".form-section").forEach((node) => mark(node, "vetedge-edge-form-section", "form-section"));
		page.querySelectorAll(".section-head").forEach((node) => mark(node, "vetedge-edge-section-head"));
		page.querySelectorAll(".form-tabs-list, .nav-tabs").forEach((node) => mark(node, "vetedge-edge-tabs", "tabs"));
		page.querySelectorAll(".grid, .form-grid").forEach((node) => mark(node, "vetedge-edge-grid", "child-table"));
		page.querySelectorAll(".grid-row").forEach((node) => mark(node, "vetedge-edge-grid-row"));
		page.querySelectorAll(".workflow-button, .actions-btn-group .dropdown-item").forEach((node) => mark(node, "vetedge-edge-workflow-action", "workflow-action"));
		page.querySelectorAll(".indicator-pill, .status-indicator").forEach((node) => mark(node, "vetedge-edge-status", "status"));
		page.querySelectorAll(".timeline, .form-timeline").forEach((node) => mark(node, "vetedge-edge-timeline", "timeline"));

		if (context.kind === "settings") enhanceSettingsIntro(page);
	}

	function enhanceSettingsIntro(page) {
		const formLayout = page.querySelector(".form-layout") || page.querySelector(".layout-main-section");
		if (!formLayout || formLayout.querySelector(".vetedge-edge-settings-intro")) return;

		const intro = document.createElement("section");
		intro.className = "vetedge-edge-settings-intro";
		intro.dataset.edgeRole = "settings-introduction";
		intro.innerHTML = [
			'<div class="vetedge-edge-settings-intro__icon" aria-hidden="true">⚙</div>',
			'<div><strong>Veterinary Settings</strong>',
			'<p>Changes apply to Veterinary workflows. Review billing, payment, notification, stock, and clinical controls carefully before saving.</p></div>',
		].join("");
		formLayout.prepend(intro);
	}

	function enhanceDialogs(context) {
		if (!context) return;
		document.querySelectorAll(".modal.show, .modal.in").forEach((modal) => {
			mark(modal, "vetedge-edge-modal", "dialog");
			mark(modal.querySelector(".modal-dialog"), "vetedge-edge-modal-dialog");
			mark(modal.querySelector(".modal-content"), "vetedge-edge-modal-content");
			mark(modal.querySelector(".modal-header"), "vetedge-edge-modal-header");
			mark(modal.querySelector(".modal-body"), "vetedge-edge-modal-body");
			mark(modal.querySelector(".modal-footer"), "vetedge-edge-modal-footer");
			modal.querySelectorAll(".btn-primary").forEach((button) => mark(button, "vetedge-edge-primary-action", "dialog-primary-action"));
		});
	}

	function apply() {
		state.lastError = null;
		try {
			patchNavigationAdapter();
			const context = currentContext();
			state.lastContext = context;
			if (!context) {
				clearBodyContext();
				return false;
			}

			const page = visiblePage();
			if (!page) return false;
			applyBodyContext(context);
			mark(page, "vetedge-edge-page", context.kind);
			enhanceHeader(page, context);
			if (context.kind === "list") enhanceList(page);
			else enhanceForm(page, context);
			enhanceDialogs(context);
			state.installed = true;
			return true;
		} catch (error) {
			state.lastError = error?.message || String(error);
			return false;
		}
	}

	function scheduleApply() {
		window.clearTimeout(state.scheduled);
		state.scheduled = window.setTimeout(apply, 0);
	}

	function startObserver() {
		if (state.observer || !window.MutationObserver || !document.body) return;
		state.observer = new MutationObserver(() => {
			if (state.lastContext || currentContext()) scheduleApply();
		});
		state.observer.observe(document.body, { childList: true, subtree: true });
	}

	function bindLifecycle() {
		ROUTE_EVENTS.forEach((eventName) => document.addEventListener(eventName, scheduleApply));
		window.frappe?.router?.on?.("change", scheduleApply);
	}

	function diagnose() {
		return {
			version: ASSET_VERSION,
			installed: state.installed,
			navigationPatched: state.navigationPatched,
			observerActive: Boolean(state.observer),
			context: state.lastContext
				? { doctype: state.lastContext.doctype, kind: state.lastContext.kind }
				: null,
			lastError: state.lastError,
		};
	}

	window.VetEdgeDeskUI = Object.assign(window.VetEdgeDeskUI || {}, {
		apply,
		diagnose,
		isNativeVetEdgePath,
	});

	bindLifecycle();
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", () => {
			startObserver();
			scheduleApply();
		}, { once: true });
	} else {
		startObserver();
		scheduleApply();
	}
})();
