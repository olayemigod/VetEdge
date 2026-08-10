// VetEdge professional EdgeSuite UI 0.2 consumer adapter.
// Business rules remain in VetEdge; this file only supplies navigation and shell presentation.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const ASSET_VERSION = "20260719-1";
	const STYLE_ID = "vetedge-professional-ui-style";
	const STYLE_URL = `/assets/vetedge/css/vetedge_professional_ui.css?v=${ASSET_VERSION}`;
	const SECTION_STATE_KEY = "edgeui:vetedge:sidebar-sections";
	const LIFECYCLE_EVENTS = ["desktop_screen", "sidebar_setup", "toolbar_setup", "page-change"];
	const BELL_MARKUP = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path></svg>';

	const SECTION_META = Object.freeze({
		Dashboard: { icon: "chart", description: "Performance, operations, and management dashboards" },
		"Front Desk": { icon: "calendar", description: "Appointments, patients, customers, invoices, and payments" },
		Clinical: { icon: "activity", description: "Consultations, medical records, laboratory, and vaccination" },
		"Hospital & Services": { icon: "building", description: "Hospitalisation, boarding, grooming, and care services" },
		"Inventory & Pharmacy": { icon: "layers", description: "Dispensary, inventory, batches, and stock monitoring" },
		Inventory: { icon: "layers", description: "Dispensary, inventory, batches, and stock monitoring" },
		Reports: { icon: "report", description: "Operational, clinical, stock, and financial reports" },
		Setup: { icon: "settings", description: "Veterinary configuration, masters, and administration" },
		Administration: { icon: "settings", description: "Veterinary configuration, masters, and administration" },
	});

	const ITEM_META = Object.freeze({
		"Executive Dashboard": { icon: "chart", description: "Branch-aware operational and financial overview" },
		"Clinical Dashboard": { icon: "activity", description: "Clinical workload and patient-care overview" },
		"Financial Dashboard": { icon: "wallet", description: "Revenue, receivables, and payment performance" },
		"Inventory / Dispensary Dashboard": { icon: "layers", description: "Stock, dispensary, and inventory performance" },
		"Stock Expiry Monitor": { icon: "layers", description: "Track expired and soon-to-expire batch stock" },
		"Appointment Queue": { icon: "calendar", description: "Run the live front-desk appointment queue" },
		Patients: { icon: "students", description: "Veterinary patient records and profiles" },
		Appointments: { icon: "calendar", description: "Schedule and manage veterinary appointments" },
		Consultations: { icon: "clipboard", description: "Clinical consultation records and treatment workflow" },
		"Medical History": { icon: "report", description: "Review longitudinal patient medical history" },
		"Vital Signs": { icon: "activity", description: "Review and manage veterinary vital-sign records" },
		"Lab Orders": { icon: "assessment", description: "Laboratory requests, billing, and results" },
		"Vaccination Records": { icon: "shield", description: "Vaccination history and due-date tracking" },
		Hospitalisations: { icon: "building", description: "Admissions, care activities, charges, and discharge" },
		"Pet Boarding Booking": { icon: "calendar", description: "Boarding reservations and service planning" },
		"Veterinary Settings": { icon: "settings", description: "Configure veterinary workflows and controls" },
	});

	const ICON_ALIASES = Object.freeze({
		"bar-chart": "chart",
		"building-2": "building",
		"calendar-days": "calendar",
		"calendar-x": "calendar",
		customer: "user",
		"file-question-mark": "clipboard",
		"file-text": "report",
		hospital: "building",
		hotel: "building",
		"list-tree": "list",
		"money-coins-1": "wallet",
		"notepad-text": "clipboard",
		pill: "layers",
		"receipt-text": "report",
		scissors: "activity",
		"scroll-text": "report",
		"shield-check": "shield",
		stethoscope: "activity",
		"user-round-search": "user",
		"users-round": "students",
	});

	const state = {
		installed: false,
		runtimeVersion: "",
		lastError: null,
		menuGroups: [],
		observerActive: false,
		lifecycleBound: false,
		legacyMenuPatched: false,
		scheduled: null,
	};

	function runtime() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	}

	function versionSupportsProfessionalUI(version) {
		const parts = String(version || "0.0.0").split(".").map((value) => Number.parseInt(value, 10) || 0);
		return parts[0] > 0 || (parts[0] === 0 && parts[1] >= 2);
	}

	function canonicalSidebar() {
		const sidebars = window.frappe?.boot?.workspace_sidebar_item;
		return sidebars && (sidebars.veterinary || sidebars.vetedge);
	}

	function slug(value) {
		const text = String(value || "").trim();
		try {
			const resolved = window.frappe?.router?.slug?.(text);
			if (resolved) return resolved;
		} catch (_error) {
			// Use the deterministic fallback below.
		}
		return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
	}

	function semanticIcon(icon, label, fallback = "list") {
		const fromLabel = ITEM_META[label]?.icon;
		if (fromLabel) return fromLabel;
		const normalized = String(icon || "").replace(/^icon-/, "").toLowerCase();
		return ICON_ALIASES[normalized] || normalized || fallback;
	}

	function shellRoute(item) {
		if (item.route) return item.route;
		const target = String(item.link_to || "").trim();
		if (!target) return "";
		if (item.link_type === "Report") return `/app/query-report/${encodeURIComponent(target)}`;
		if (item.link_type === "DocType") return `/app/${slug(target)}`;
		return `/app/${target.replace(/^\/+/, "")}`;
	}

	function itemDescription(item) {
		return ITEM_META[item.label]?.description || String(item.description || item.link_type || "Veterinary workspace");
	}

	function fallbackGroups() {
		return [
			{
				key: "overview",
				label: "Overview",
				icon: "home",
				description: "Veterinary operations and inventory overview",
				items: [
					{ label: "Executive Dashboard", route: "/app/vetedge-executive-dashboard", icon: "chart", description: ITEM_META["Executive Dashboard"].description, link_type: "Page", link_to: "vetedge-executive-dashboard" },
					{ label: "Stock Expiry Monitor", route: "/app/stock-expiry-monitor", icon: "layers", description: ITEM_META["Stock Expiry Monitor"].description, link_type: "Page", link_to: "stock-expiry-monitor" },
				],
			},
			{
				key: "administration",
				label: "Administration",
				icon: "settings",
				description: "Veterinary configuration and controls",
				defaultCollapsed: true,
				items: [
					{ label: "Veterinary Settings", route: "/app/veterinary-settings", icon: "settings", description: ITEM_META["Veterinary Settings"].description, link_type: "DocType", link_to: "Veterinary Settings" },
				],
			},
		];
	}

	function getMenuItems() {
		const sourceItems = canonicalSidebar()?.items;
		if (!Array.isArray(sourceItems) || !sourceItems.length) return fallbackGroups();

		const groups = [];
		let group = null;
		for (const source of sourceItems) {
			if (!source || source.hidden === 1) continue;
			if (source.type === "Section Break") {
				const meta = SECTION_META[source.label] || {};
				group = {
					key: slug(source.label || `section-${groups.length + 1}`),
					label: source.label || "Navigation",
					icon: semanticIcon(source.icon, "", meta.icon || "layers"),
					description: meta.description || `${source.label || "Veterinary"} workspace`,
					defaultCollapsed: Boolean(source.keep_closed),
					items: [],
				};
				groups.push(group);
				continue;
			}
			if (source.type !== "Link") continue;
			if (!group) {
				group = { key: "navigation", label: "Navigation", icon: "grid", description: "Veterinary workspace", items: [] };
				groups.push(group);
			}
			const item = {
				label: source.label || source.link_to,
				icon: semanticIcon(source.icon, source.label),
				description: itemDescription(source),
				link_type: source.link_type || "Page",
				link_to: source.link_to || "",
				roles: Array.isArray(source.roles) ? source.roles : [],
				badge: source.badge || "",
			};
			item.route = shellRoute(item);
			if (item.label && item.route) group.items.push(item);
		}
		const populated = groups.filter((entry) => entry.items.length);
		return populated.length ? populated : fallbackGroups();
	}

	function profile() {
		const boot = window.frappe?.boot || {};
		const user = window.frappe?.session?.user || boot.user?.name || "";
		const userInfo = boot.user_info?.[user] || {};
		return {
			name: userInfo.fullname || userInfo.full_name || boot.user?.full_name || user || "Veterinary User",
			email: user,
			company: boot.sysdefaults?.company || window.frappe?.defaults?.get_default?.("company") || "",
			branch:
				boot.edgesuite_product_menu?.branch ||
				window.frappe?.defaults?.get_user_default?.("branch") ||
				"All Branches",
		};
	}

	function productMenuSections(groups) {
		return groups.map((group) => ({
			label: group.label,
			description: group.description || "",
			icon: group.icon || "layers",
			items: group.items.map((item) => ({
				label: item.label,
				description: item.description || "",
				icon: item.icon || "list",
				badge: item.badge || "",
				roles: item.roles || [],
				keywords: [item.label, group.label, item.link_to].filter(Boolean),
				link_type: item.link_type,
				link_to: item.link_to,
				route: item.link_type === "Page" ? item.route : "",
			})),
		}));
	}

	function openRoute(route) {
		const target = String(route || "").trim();
		if (!target) return;
		window.location.assign(target);
	}

	function injectStyles() {
		if (document.getElementById(STYLE_ID)) return;
		const link = document.createElement("link");
		link.id = STYLE_ID;
		link.rel = "stylesheet";
		link.href = STYLE_URL;
		document.head.appendChild(link);
	}

	function enhanceNotificationIcons(root = document) {
		root.querySelectorAll?.(".vetedge-notification-icon").forEach((node) => {
			if (node.dataset.vetedgeProfessionalIcon === "1") return;
			node.dataset.vetedgeProfessionalIcon = "1";
			node.innerHTML = BELL_MARKUP;
		});
	}

	function startObserver() {
		if (state.observerActive || !window.MutationObserver || !document.body) return;
		const observer = new MutationObserver((records) => {
			for (const record of records) {
				for (const node of record.addedNodes || []) {
					if (!(node instanceof HTMLElement)) continue;
					enhanceNotificationIcons(node);
				}
			}
		});
		observer.observe(document.body, { childList: true, subtree: true });
		state.observerActive = true;
	}

	function registerProductMenu(edgeUI, groups) {
		if (typeof edgeUI.registerProductMenu !== "function") return;
		edgeUI.registerProductMenu({
			product: "vetedge",
			label: "Veterinary",
			title: "Veterinary",
			icon: "stethoscope",
			sections: productMenuSections(groups),
			profile: profile(),
			navigate(item) {
				const route = shellRoute(item || {});
				if (!route) return;
				const navigation = edgeUI.getAdapter?.("navigation:vetedge");
				if (navigation?.open?.(route) === true) return;
				openRoute(route);
			},
		});
	}

	function install() {
		state.lastError = null;
		const edgeUI = runtime();
		state.runtimeVersion = edgeUI?.version || "";
		if (!edgeUI?.components || !versionSupportsProfessionalUI(edgeUI.version)) {
			state.installed = false;
			state.lastError = `VetEdge requires EdgeSuite UI 0.2 or newer; found ${edgeUI?.version || "unknown"}.`;
			return { installed: false, message: state.lastError };
		}
		injectStyles();
		state.menuGroups = getMenuItems();
		registerProductMenu(edgeUI, state.menuGroups);
		startObserver();
		state.installed = true;
		return { installed: true, menuGroups: state.menuGroups };
	}

	function scheduleInstall() {
		if (state.scheduled) window.clearTimeout(state.scheduled);
		state.scheduled = window.setTimeout(() => {
			state.scheduled = null;
			install();
		}, 50);
	}

	function bindLifecycle() {
		if (state.lifecycleBound) return;
		for (const eventName of LIFECYCLE_EVENTS) document.addEventListener(eventName, scheduleInstall);
		window.frappe?.router?.on?.("change", scheduleInstall);
		state.lifecycleBound = true;
	}

	window.VetEdgeProfessionalUI = Object.assign(window.VetEdgeProfessionalUI || {}, {
		install,
		getMenuItems,
		profile,
		diagnose() {
			return {
				installed: state.installed,
				runtimeVersion: state.runtimeVersion,
				lastError: state.lastError,
				menuGroups: state.menuGroups,
			};
		},
	});

	bindLifecycle();
	if (!install()) {
		document.addEventListener("DOMContentLoaded", install, { once: true });
		window.setTimeout(install, 250);
	}
})();
