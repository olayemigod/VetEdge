// Canonical VetEdge navigation recovery for the post-consolidation QA branch.
//
// The accepted EdgeSuite migrations already exist in VetEdge, but the sidebar
// still exposes several native DocType/Page targets and relies on multiple
// redirect layers to reach those migrated surfaces. This late adapter makes the
// accepted destination explicit and gives the shared EdgeAppShell one routing
// path. Business logic and backend permission rules remain unchanged.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const PRODUCT_KEYS = new Set(["vetedge", "veterinary"]);
	const LIFECYCLE_EVENTS = ["desktop_screen", "sidebar_setup", "toolbar_setup", "page-change"];

	const ACCEPTED_EDGEUI_ROUTES = Object.freeze({
		"Page:veterinary-appointment-queue": "/app/vetedge-front-desk-action-center?tab=queue",
		"DocType:Veterinary Patient": "/app/vetedge-resource-center?resource=patients",
		"DocType:Veterinary Appointment": "/app/vetedge-resource-center?resource=appointments",
		"DocType:Veterinary Guest Booking Request": "/app/vetedge-front-desk-action-center?tab=guest",
		"DocType:Veterinary Missed Appointment": "/app/vetedge-front-desk-action-center?tab=missed",
		"DocType:Veterinary Consultation": "/app/vetedge-clinical-workspace",
		"DocType:Veterinary Lab Order": "/app/vetedge-resource-center?resource=lab-orders",
		"DocType:Veterinary Vaccination Record": "/app/vetedge-resource-center?resource=vaccinations",
		"DocType:Pet Grooming Appointment": "/app/vetedge-resource-center?resource=grooming",
		"DocType:Pet Boarding Booking": "/app/vetedge-resource-center?resource=boarding",
		"DocType:Kennel": "/app/vetedge-resource-center?resource=kennels",
		"DocType:Veterinary Settings": "/app/veterinary-settings-center",
		"DocType:Veterinary Species": "/app/vetedge-master-workspace?resource=species",
		"DocType:Veterinary Breed": "/app/vetedge-master-workspace?resource=breeds",
		"DocType:Veterinary Symptom": "/app/vetedge-master-workspace?resource=symptoms",
		"DocType:Veterinary Diagnosis Category": "/app/vetedge-master-workspace?resource=diagnosis-categories",
		"DocType:Veterinary Diagnosis": "/app/vetedge-master-workspace?resource=diagnoses",
		"DocType:Veterinary Service Type": "/app/vetedge-master-workspace?resource=service-types",
		"DocType:Consultation Type": "/app/vetedge-master-workspace?resource=consultation-types",
		"DocType:Veterinary Treatment Item": "/app/vetedge-pricing-master-workspace?resource=treatment-items",
		"DocType:Veterinary Treatment Type": "/app/vetedge-pricing-master-workspace?resource=treatment-types",
		"DocType:Veterinary Lab Test": "/app/vetedge-pricing-master-workspace?resource=lab-tests",
		"DocType:Veterinary Vaccine": "/app/vetedge-pricing-master-workspace?resource=vaccines",
		"DocType:Pet Grooming Service": "/app/vetedge-pricing-master-workspace?resource=grooming-services",
		"Page:kennel-availability": "/app/vetedge-service-operations?resource=availability",
		"Page:kennel-availability-board": "/app/vetedge-service-operations?resource=availability",
		"DocType:Pet Boarding Stay": "/app/vetedge-service-operations?resource=boarding-stays",
		"DocType:Pet Boarding Care Record": "/app/vetedge-service-operations?resource=boarding-care-records",
		"DocType:Pet Grooming Session": "/app/vetedge-service-operations?resource=grooming-sessions",
	});

	const HOME_GROUP = Object.freeze({
		key: "home",
		label: "Home",
		icon: "home",
		description: "Veterinary home and daily operations",
		defaultCollapsed: false,
		items: [
			{
				label: "Veterinary Home",
				icon: "home",
				description: "Open the Veterinary home and resource centre",
				link_type: "Page",
				link_to: "vetedge",
				route: "/app/vetedge",
				roles: [],
				badge: "",
			},
		],
	});

	const state = {
		installed: false,
		shellPatched: false,
		menuPatched: false,
		lifecycleBound: false,
		lastError: null,
	};

	function runtime() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	}

	function canonicalSidebar() {
		const sidebars = window.frappe?.boot?.workspace_sidebar_item;
		return sidebars && (sidebars.vetedge || sidebars.veterinary);
	}

	function slug(value) {
		const text = String(value || "").trim();
		try {
			const resolved = window.frappe?.router?.slug?.(text);
			if (resolved) return resolved;
		} catch (_error) {
			// Deterministic fallback below.
		}
		return text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
	}

	function routeKey(item) {
		return `${String(item?.link_type || item?.linkType || "Page")}:${String(item?.link_to || item?.linkTo || "").trim()}`;
	}

	function canonicalRoute(item) {
		const accepted = ACCEPTED_EDGEUI_ROUTES[routeKey(item)];
		if (accepted) return accepted;

		const supplied = String(item?.route || "").trim();
		if (supplied) return supplied.startsWith("/") ? supplied : `/app/${supplied.replace(/^\/+/, "")}`;

		const target = String(item?.link_to || item?.linkTo || "").trim();
		if (!target) return "";
		const type = String(item?.link_type || item?.linkType || "Page");
		if (type === "Report") return `/app/query-report/${encodeURIComponent(target)}`;
		if (type === "DocType") return `/app/${slug(target)}`;
		return `/app/${target.replace(/^\/+/, "")}`;
	}

	function normalizeItem(item) {
		return {
			...item,
			link_type: item?.link_type || item?.linkType || "Page",
			link_to: item?.link_to || item?.linkTo || "",
			route: canonicalRoute(item),
		};
	}

	function hasHome(groups) {
		return (groups || []).some((group) =>
			(group.items || []).some((item) => item?.link_to === "vetedge" || item?.route === "/app/vetedge")
		);
	}

	function rewriteGroups(groups) {
		const rewritten = (Array.isArray(groups) ? groups : []).map((group) => ({
			...group,
			items: (group.items || []).map(normalizeItem).filter((item) => item.label && item.route),
		})).filter((group) => group.items.length);

		if (!hasHome(rewritten)) rewritten.unshift({ ...HOME_GROUP, items: HOME_GROUP.items.map((item) => ({ ...item })) });
		return rewritten;
	}

	function groupsFromSidebar() {
		const sourceItems = canonicalSidebar()?.items;
		if (!Array.isArray(sourceItems) || !sourceItems.length) return rewriteGroups([]);

		const groups = [];
		let group = null;
		for (const source of sourceItems) {
			if (!source || source.hidden === 1) continue;
			if (source.type === "Section Break") {
				group = {
					key: slug(source.label || `section-${groups.length + 1}`),
					label: source.label || "Navigation",
					icon: source.icon || "layers",
					description: source.description || "Veterinary workspace",
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
			group.items.push(normalizeItem({
				label: source.label || source.link_to,
				icon: source.icon || "list",
				description: source.description || source.link_type || "Veterinary workspace",
				link_type: source.link_type || "Page",
				link_to: source.link_to || "",
				roles: Array.isArray(source.roles) ? source.roles : [],
				badge: source.badge || "",
			}));
		}
		return rewriteGroups(groups);
	}

	function applyDeskRoute(target) {
		const route = String(target || "").trim();
		if (!route) return false;

		try {
			const url = new URL(route, window.location.origin);
			if (url.origin !== window.location.origin || !/^\/(?:app|desk)(?:\/|$)/.test(url.pathname)) {
				window.location.assign(route);
				return true;
			}

			if (typeof window.frappe?.set_route !== "function") {
				window.location.assign(route);
				return true;
			}

			window.frappe.route_options = {};
			for (const [key, value] of url.searchParams) window.frappe.route_options[key] = value;
			window.frappe.route_hash = url.hash || null;

			const parts = url.pathname
				.replace(/^\/(?:app|desk)(?:\/|$)/, "")
				.split("/")
				.filter(Boolean)
				.map(decodeURIComponent);
			if (!parts.length) return false;
			window.frappe.set_route(...parts);
			return true;
		} catch (error) {
			state.lastError = error?.message || String(error);
			window.location.assign(route);
			return true;
		}
	}

	function installShellPatch(edgeUI) {
		if (edgeUI.__vetedgeCanonicalNavigationShellInstalled) {
			state.shellPatched = true;
			return true;
		}
		const InnerShell = edgeUI.components?.EdgeAppShell;
		const Vue = edgeUI.Vue;
		if (!InnerShell || !Vue?.defineComponent || !Vue?.h || typeof edgeUI.registerComponent !== "function") return false;

		const CanonicalVetEdgeShell = Vue.defineComponent({
			name: "CanonicalVetEdgeShell",
			inheritAttrs: false,
			setup(_props, context) {
				return () => {
					const attrs = context.attrs || {};
					const groups = rewriteGroups(
						Array.isArray(attrs.menuItems) && attrs.menuItems.length ? attrs.menuItems : groupsFromSidebar()
					);
					return Vue.h(
						InnerShell,
						{
							...attrs,
							menuItems: groups,
							onNavigate: (route) => applyDeskRoute(route),
						},
						context.slots
					);
				};
			},
		});

		edgeUI.registerComponent("EdgeAppShell", CanonicalVetEdgeShell, { replace: true });
		edgeUI.__vetedgeCanonicalNavigationShellInstalled = true;
		state.shellPatched = true;
		return true;
	}

	function rewriteProductMenuConfig(config) {
		const product = String(config?.product || "").trim().toLowerCase();
		if (!PRODUCT_KEYS.has(product)) return config;

		const groups = rewriteGroups(
			(config.sections || []).map((section) => ({
				...section,
				items: section.items || [],
			}))
		);
		return {
			...config,
			sections: groups.map((group) => ({
				label: group.label,
				description: group.description || "",
				icon: group.icon || "layers",
				items: group.items.map((item) => ({ ...item, route: canonicalRoute(item) })),
			})),
		};
	}

	function installProductMenuPatch(edgeUI) {
		if (edgeUI.__vetedgeCanonicalNavigationMenuPatched) {
			state.menuPatched = true;
			return true;
		}
		if (typeof edgeUI.registerProductMenu !== "function") return false;

		const previousRegister = edgeUI.registerProductMenu.bind(edgeUI);
		edgeUI.registerProductMenu = function registerCanonicalVetEdgeMenu(config) {
			return previousRegister(rewriteProductMenuConfig(config));
		};
		edgeUI.__vetedgeCanonicalNavigationMenuPatched = true;
		state.menuPatched = true;

		const current = edgeUI.getProductMenuConfig?.();
		if (current && PRODUCT_KEYS.has(String(current.product || "").trim().toLowerCase())) {
			edgeUI.registerProductMenu(current);
			edgeUI.refreshProductMenu?.();
		}
		return true;
	}

	function install() {
		state.lastError = null;
		const edgeUI = runtime();
		if (!edgeUI) return false;
		try {
			installShellPatch(edgeUI);
			installProductMenuPatch(edgeUI);
			state.installed = state.shellPatched && state.menuPatched;
			return state.installed;
		} catch (error) {
			state.lastError = error?.message || String(error);
			return false;
		}
	}

	function scheduleInstall() {
		window.setTimeout(install, 0);
	}

	function bindLifecycle() {
		if (state.lifecycleBound) return;
		state.lifecycleBound = true;
		LIFECYCLE_EVENTS.forEach((eventName) => document.addEventListener(eventName, scheduleInstall));
		window.frappe?.router?.on?.("change", scheduleInstall);
	}

	function diagnose() {
		return {
			...state,
			homePresent: hasHome(groupsFromSidebar()),
			menuGroupCount: groupsFromSidebar().length,
		};
	}

	window.VetEdgeNavigationRecovery = {
		install,
		diagnose,
		canonicalRoute,
		groupsFromSidebar,
		navigate: applyDeskRoute,
	};

	bindLifecycle();
	if (window.frappe?.require) {
		window.frappe.require("edgeui.bundle.js", scheduleInstall);
	} else if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", scheduleInstall, { once: true });
	} else {
		scheduleInstall();
	}
})();
