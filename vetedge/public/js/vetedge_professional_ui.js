// VetEdge professional EdgeSuite UI consumer adapter.
// Business rules remain in VetEdge; this file only supplies navigation and shell presentation.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const ASSET_VERSION = "20260723-2";
	const STYLE_ID = "vetedge-professional-ui-style";
	const STYLE_URL = `/assets/vetedge/css/vetedge_professional_ui.css?v=${ASSET_VERSION}`;
	const SECTION_STATE_KEY = "edgeui:vetedge:sidebar-sections";
	const LIFECYCLE_EVENTS = ["desktop_screen", "sidebar_setup", "toolbar_setup", "page-change"];
	const BELL_MARKUP = '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"></path></svg>';
	const TECHNICAL_DESCRIPTIONS = new Set(["doctype", "page", "report", "link", "workspace sidebar"]);

	const SECTION_META = Object.freeze({
		Dashboard: { icon: "chart", description: "Performance and operational overview" },
		"Front Desk": { icon: "calendar", description: "Appointments, patients and payments" },
		Clinical: { icon: "activity", description: "Consultations and patient care" },
		"Hospital & Services": { icon: "building", description: "Hospital, boarding and grooming" },
		"Inventory & Pharmacy": { icon: "layers", description: "Dispensary and stock control" },
		Inventory: { icon: "layers", description: "Dispensary and stock control" },
		Reports: { icon: "report", description: "Operational and management reports" },
		"Veterinary Masters": { icon: "list", description: "Clinical reference records" },
		Setup: { icon: "settings", description: "Configuration and administration" },
		Configuration: { icon: "settings", description: "Configuration and administration" },
		Administration: { icon: "settings", description: "Configuration and administration" },
		Platform: { icon: "grid", description: "Platform access and services" },
		"Help & Training": { icon: "help", description: "Guides and staff training" },
	});

	const ITEM_META = Object.freeze({
		"Veterinary Home": { icon: "home", description: "Return to the main workspace" },
		"Executive Dashboard": { icon: "chart", description: "Clinic performance overview" },
		"Clinical Dashboard": { icon: "activity", description: "Clinical workload overview" },
		"Financial Dashboard": { icon: "wallet", description: "Revenue and payment performance" },
		"Inventory / Dispensary Dashboard": { icon: "layers", description: "Stock and dispensary overview" },
		"Lab Dashboard": { icon: "assessment", description: "Laboratory workload overview" },
		"Vaccination Dashboard": { icon: "shield", description: "Vaccination activity overview" },
		"Boarding Dashboard": { icon: "building", description: "Boarding activity overview" },
		"Grooming Dashboard": { icon: "activity", description: "Grooming activity overview" },
		"Practitioner Performance Dashboard": { icon: "user", description: "Practitioner workload and results" },
		"Branch Performance Dashboard": { icon: "building", description: "Compare branch performance" },
		"Stock Expiry Monitor": { icon: "layers", description: "Review expiring batch stock" },
		"Appointment Queue": { icon: "calendar", description: "Run the live appointment queue" },
		Patients: { icon: "students", description: "Manage veterinary patients" },
		Appointments: { icon: "calendar", description: "Schedule and manage appointments" },
		"Guest Booking Requests": { icon: "clipboard", description: "Review owner booking requests" },
		"Missed Appointments": { icon: "calendar", description: "Resolve missed appointments" },
		Customer: { icon: "user", description: "Manage pet owner accounts" },
		"Sales Invoice": { icon: "report", description: "Review veterinary invoices" },
		"Payment Entry": { icon: "wallet", description: "Record and review payments" },
		Consultations: { icon: "clipboard", description: "Run clinical consultations" },
		"Medical History": { icon: "report", description: "Review patient medical history" },
		"Vital Signs": { icon: "activity", description: "Record patient vital signs" },
		"Lab Orders": { icon: "assessment", description: "Manage tests and results" },
		"Vaccination Records": { icon: "shield", description: "Manage vaccination records" },
		Hospitalisations: { icon: "building", description: "Manage admissions and discharge" },
		"Kennel Availability Board": { icon: "building", description: "View available care locations" },
		"Pet Boarding Booking": { icon: "calendar", description: "Manage boarding reservations" },
		"Pet Boarding Stay": { icon: "building", description: "Manage active boarding stays" },
		"Pet Boarding Care Record": { icon: "clipboard", description: "Record boarding care" },
		"Pet Grooming Appointment": { icon: "calendar", description: "Schedule grooming services" },
		"Pet Grooming Session": { icon: "activity", description: "Run grooming sessions" },
		Item: { icon: "layers", description: "Manage stock and service items" },
		Species: { icon: "activity", description: "Maintain animal species" },
		Breeds: { icon: "list", description: "Maintain species-specific breeds" },
		Symptoms: { icon: "activity", description: "Maintain clinical symptoms" },
		Diagnoses: { icon: "clipboard", description: "Maintain standard diagnoses" },
		"Diagnosis Categories": { icon: "layers", description: "Organise diagnosis records" },
		"Service Types": { icon: "tool", description: "Maintain veterinary service types" },
		"Consultation Types": { icon: "clipboard", description: "Maintain consultation options" },
		"Treatment Items": { icon: "layers", description: "Maintain treatment billing items" },
		"Treatment Types": { icon: "settings", description: "Maintain treatment categories" },
		"Lab Tests": { icon: "assessment", description: "Maintain laboratory test catalogue" },
		Vaccines: { icon: "shield", description: "Maintain vaccine catalogue" },
		"Pet Grooming Service": { icon: "activity", description: "Maintain grooming services" },
		Settings: { icon: "settings", description: "Configure Veterinary operations" },
		"Veterinary Settings": { icon: "settings", description: "Configure Veterinary operations" },
		Branch: { icon: "building", description: "Manage clinic branches" },
		"Care Locations": { icon: "building", description: "Manage hospital care locations" },
		Kennel: { icon: "building", description: "Manage kennels and capacity" },
		"Branch User Assignment": { icon: "students", description: "Assign users to branches" },
		"Branch Practitioner Assignment": { icon: "user", description: "Assign practitioners to branches" },
		"Training Centre": { icon: "help", description: "Open staff training guides" },
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

	function shortDescription(value) {
		const text = String(value || "").replace(/\s+/g, " ").trim();
		if (!text || TECHNICAL_DESCRIPTIONS.has(text.toLowerCase())) return "";
		return text.length > 72 ? `${text.slice(0, 69).trim()}…` : text;
	}

	function itemDescription(item) {
		return shortDescription(ITEM_META[item.label]?.description || item.description || "");
	}

	function fallbackGroups() {
		return [
			{
				key: "overview",
				label: "Overview",
				icon: "home",
				description: "Veterinary operations overview",
				items: [
					{ label: "Veterinary Home", route: "/app/vetedge", icon: "home", description: ITEM_META["Veterinary Home"].description, link_type: "Page", link_to: "vetedge" },
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
					description: shortDescription(meta.description || source.description || ""),
					defaultCollapsed: Boolean(source.keep_closed),
					items: [],
				};
				groups.push(group);
				continue;
			}
			if (source.type !== "Link") continue;
			if (!group) {
				group = { key: "navigation", label: "Navigation", icon: "grid", description: "", items: [] };
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
			item.route = shellRoute({ ...item, route: source.route || "" });
			if (item.label && item.route) group.items.push(item);
		}
		const populated = groups.filter((entry) => entry.items.length);
		return populated.length ? populated : fallbackGroups();
	}

	function compactShellGroups(groups) {
		return (groups || []).map((group) => ({
			...group,
			description: "",
			items: (group.items || []).map((item) => ({ ...item, description: "" })),
		}));
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
			description: shortDescription(group.description || ""),
			icon: group.icon || "layers",
			items: group.items.map((item) => ({
				label: item.label,
				description: shortDescription(item.description || ""),
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
					if (node.nodeType === 1) enhanceNotificationIcons(node);
				}
			}
		});
		observer.observe(document.body, { childList: true, subtree: true });
		state.observerActive = true;
	}

	function installShellAdapter(edgeUI, groups) {
		if (edgeUI.__vetedgeProfessionalShellInstalled) return true;
		const OriginalShell = edgeUI.components?.EdgeAppShell;
		const Vue = edgeUI.Vue;
		if (!OriginalShell || !Vue?.defineComponent || !Vue?.h || !edgeUI.registerComponent) return false;

		const ProfessionalVetEdgeShell = Vue.defineComponent({
			name: "ProfessionalVetEdgeShell",
			inheritAttrs: false,
			setup(_props, context) {
				return () => {
					const attrs = context.attrs || {};
					const sourceMenu = Array.isArray(attrs.menuItems) && attrs.menuItems.length ? attrs.menuItems : groups;
					const suppliedMenu = compactShellGroups(sourceMenu);
					const suppliedNavigate = attrs.onNavigate;
					const onNavigate = (route) => {
						let handled = false;
						const listeners = Array.isArray(suppliedNavigate) ? suppliedNavigate : [suppliedNavigate];
						listeners.forEach((listener) => {
							if (typeof listener === "function") {
								listener(route);
								handled = true;
							}
						});
						if (!handled) openRoute(route);
					};
					return Vue.h(
						OriginalShell,
						{
							...attrs,
							menuItems: suppliedMenu,
							subtitle: attrs.subtitle || "Veterinary Practice Management",
							hideNativeSidebar: attrs.hideNativeSidebar ?? true,
							sectionStateKey: attrs.sectionStateKey || SECTION_STATE_KEY,
							onNavigate,
						},
						context.slots
					);
				};
			},
		});

		edgeUI.registerComponent("EdgeAppShell", ProfessionalVetEdgeShell, { replace: true });
		edgeUI.__vetedgeProfessionalShellInstalled = true;
		return true;
	}

	function registerProfessionalMenu(edgeUI, groups) {
		if (typeof edgeUI.registerProductMenu !== "function") return false;
		edgeUI.registerProductMenu({
			product: "VetEdge",
			subtitle: "Veterinary practice operations",
			menu_source: "vetedge-professional",
			profile: profile(),
			sections: productMenuSections(groups),
		});
		edgeUI.refreshProductMenu?.();
		return true;
	}

	function patchLegacyMenu() {
		const legacy = window.VetedgeProductMenu;
		if (!legacy || legacy.__professionalMenuPatched) return;
		for (const methodName of ["mount", "remount"]) {
			const original = legacy[methodName];
			if (typeof original !== "function") continue;
			legacy[methodName] = function (...args) {
				const result = original.apply(this, args);
				window.setTimeout(() => {
					const edgeUI = runtime();
					if (edgeUI && state.menuGroups.length) registerProfessionalMenu(edgeUI, state.menuGroups);
				}, 0);
				return result;
			};
		}
		legacy.__professionalMenuPatched = true;
		state.legacyMenuPatched = true;
	}

	function install() {
		state.lastError = null;
		injectStyles();
		const edgeUI = runtime();
		if (!edgeUI) {
			return { installed: false, reason: "runtime-unavailable", message: "The standalone EdgeSuite UI runtime is unavailable." };
		}
		if (!versionSupportsProfessionalUI(edgeUI.version) || !edgeUI.components?.EdgeIcon) {
			return {
				installed: false,
				reason: "edgeui-0.2-required",
				message: `EdgeSuite UI 0.2 or newer is required. Loaded version: ${edgeUI.version || "unknown"}.`,
			};
		}

		try {
			const groups = getMenuItems();
			if (!installShellAdapter(edgeUI, groups)) {
				throw new Error("EdgeSuite UI does not expose the professional shell adapter contract.");
			}
			state.menuGroups = groups;
			patchLegacyMenu();
			registerProfessionalMenu(edgeUI, groups);
			enhanceNotificationIcons();
			startObserver();
			state.installed = true;
			state.runtimeVersion = edgeUI.version || "";
			return { installed: true, version: state.runtimeVersion, groups: groups.length };
		} catch (error) {
			state.lastError = error?.message || String(error);
			return { installed: false, reason: "installation-failed", message: state.lastError };
		}
	}

	function scheduleInstall(reason = "lifecycle") {
		window.clearTimeout(state.scheduled);
		state.scheduled = window.setTimeout(() => {
			const result = install();
			if (!result.installed && window.frappe?.boot?.developer_mode) {
				console.warn("[VetEdgeProfessionalUI]", reason, result);
			}
		}, 0);
	}

	function bindLifecycle() {
		if (state.lifecycleBound) return;
		state.lifecycleBound = true;
		LIFECYCLE_EVENTS.forEach((eventName) => {
			document.addEventListener(eventName, () => scheduleInstall(eventName));
		});
		window.frappe?.router?.on?.("change", () => scheduleInstall("router-change"));
	}

	function diagnose() {
		return {
			installed: state.installed,
			runtimeVersion: state.runtimeVersion,
			menuGroupCount: state.menuGroups.length,
			menuItemCount: state.menuGroups.reduce((total, group) => total + group.items.length, 0),
			observerActive: state.observerActive,
			lifecycleBound: state.lifecycleBound,
			legacyMenuPatched: state.legacyMenuPatched,
			lastError: state.lastError,
			productMenuSource: runtime()?.getProductMenuConfig?.()?.menu_source || "",
		};
	}

	window.VetEdgeProfessionalUI = Object.assign(window.VetEdgeProfessionalUI || {}, {
		install,
		getMenuItems,
		compactShellGroups,
		diagnose,
		openRoute,
	});

	bindLifecycle();
	if (window.frappe?.require) {
		window.frappe.require("edgesuite_ui.bundle.js", () => scheduleInstall("asset-ready"));
	} else if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", () => scheduleInstall("dom-ready"), { once: true });
	} else {
		scheduleInstall("initial");
	}
})();
