// Canonical VetEdge navigation for Frappe/ERPNext v16.
//
// Frappe v16 serves Desk at /desk. VetEdge previously mixed /app and /desk
// route forms across the shared shell, product menu and migration bridges. This
// adapter makes /desk authoritative while preserving native DocType/Page/Report
// semantics for destinations that have not migrated to EdgeSuite UI.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const PRODUCT_KEYS = new Set(["vetedge", "veterinary"]);
	const LIFECYCLE_EVENTS = ["desktop_screen", "sidebar_setup", "toolbar_setup", "page-change"];
	const DESK_PREFIX = "/desk";

	const ACCEPTED_EDGEUI_ROUTES = Object.freeze({
		"Page:veterinary-appointment-queue": "/desk/vetedge-front-desk-action-center?tab=queue",
		"DocType:Veterinary Patient": "/desk/vetedge-resource-center?resource=patients",
		"DocType:Veterinary Appointment": "/desk/vetedge-resource-center?resource=appointments",
		"DocType:Veterinary Guest Booking Request": "/desk/vetedge-front-desk-action-center?tab=guest",
		"DocType:Veterinary Missed Appointment": "/desk/vetedge-front-desk-action-center?tab=missed",
		"DocType:Veterinary Consultation": "/desk/vetedge-clinical-workspace",
		"DocType:Veterinary Lab Order": "/desk/vetedge-resource-center?resource=lab-orders",
		"DocType:Veterinary Vaccination Record": "/desk/vetedge-resource-center?resource=vaccinations",
		"DocType:Pet Grooming Appointment": "/desk/vetedge-resource-center?resource=grooming",
		"DocType:Pet Boarding Booking": "/desk/vetedge-resource-center?resource=boarding",
		"DocType:Kennel": "/desk/vetedge-resource-center?resource=kennels",
		"DocType:Veterinary Settings": "/desk/veterinary-settings-center",
		"DocType:Veterinary Species": "/desk/vetedge-master-workspace?resource=species",
		"DocType:Veterinary Breed": "/desk/vetedge-master-workspace?resource=breeds",
		"DocType:Veterinary Symptom": "/desk/vetedge-master-workspace?resource=symptoms",
		"DocType:Veterinary Diagnosis Category": "/desk/vetedge-master-workspace?resource=diagnosis-categories",
		"DocType:Veterinary Diagnosis": "/desk/vetedge-master-workspace?resource=diagnoses",
		"DocType:Veterinary Service Type": "/desk/vetedge-master-workspace?resource=service-types",
		"DocType:Consultation Type": "/desk/vetedge-master-workspace?resource=consultation-types",
		"DocType:Veterinary Treatment Item": "/desk/vetedge-pricing-master-workspace?resource=treatment-items",
		"DocType:Veterinary Treatment Type": "/desk/vetedge-pricing-master-workspace?resource=treatment-types",
		"DocType:Veterinary Lab Test": "/desk/vetedge-pricing-master-workspace?resource=lab-tests",
		"DocType:Veterinary Vaccine": "/desk/vetedge-pricing-master-workspace?resource=vaccines",
		"DocType:Pet Grooming Service": "/desk/vetedge-pricing-master-workspace?resource=grooming-services",
		"Page:kennel-availability": "/desk/vetedge-service-operations?resource=availability",
		"Page:kennel-availability-board": "/desk/vetedge-service-operations?resource=availability",
		"DocType:Pet Boarding Stay": "/desk/vetedge-service-operations?resource=boarding-stays",
		"DocType:Pet Boarding Care Record": "/desk/vetedge-service-operations?resource=boarding-care-records",
		"DocType:Pet Grooming Session": "/desk/vetedge-service-operations?resource=grooming-sessions",
	});

	const MIGRATED_DOCTYPES = Object.freeze({
		"Veterinary Patient": { base: "/desk/vetedge-resource-center", resource: "patients" },
		"Veterinary Appointment": { base: "/desk/vetedge-resource-center", resource: "appointments" },
		"Veterinary Lab Order": { base: "/desk/vetedge-resource-center", resource: "lab-orders" },
		"Veterinary Vaccination Record": { base: "/desk/vetedge-resource-center", resource: "vaccinations" },
		"Pet Grooming Appointment": { base: "/desk/vetedge-resource-center", resource: "grooming" },
		"Pet Boarding Booking": { base: "/desk/vetedge-resource-center", resource: "boarding" },
		Kennel: { base: "/desk/vetedge-resource-center", resource: "kennels" },
		"Veterinary Species": { base: "/desk/vetedge-master-workspace", resource: "species" },
		"Veterinary Breed": { base: "/desk/vetedge-master-workspace", resource: "breeds" },
		"Veterinary Symptom": { base: "/desk/vetedge-master-workspace", resource: "symptoms" },
		"Veterinary Diagnosis Category": { base: "/desk/vetedge-master-workspace", resource: "diagnosis-categories" },
		"Veterinary Diagnosis": { base: "/desk/vetedge-master-workspace", resource: "diagnoses" },
		"Veterinary Service Type": { base: "/desk/vetedge-master-workspace", resource: "service-types" },
		"Consultation Type": { base: "/desk/vetedge-master-workspace", resource: "consultation-types" },
		"Veterinary Treatment Item": { base: "/desk/vetedge-pricing-master-workspace", resource: "treatment-items" },
		"Veterinary Treatment Type": { base: "/desk/vetedge-pricing-master-workspace", resource: "treatment-types" },
		"Veterinary Lab Test": { base: "/desk/vetedge-pricing-master-workspace", resource: "lab-tests" },
		"Veterinary Vaccine": { base: "/desk/vetedge-pricing-master-workspace", resource: "vaccines" },
		"Pet Grooming Service": { base: "/desk/vetedge-pricing-master-workspace", resource: "grooming-services" },
		"Pet Boarding Stay": { base: "/desk/vetedge-service-operations", resource: "boarding-stays" },
		"Pet Boarding Care Record": { base: "/desk/vetedge-service-operations", resource: "boarding-care-records" },
		"Pet Grooming Session": { base: "/desk/vetedge-service-operations", resource: "grooming-sessions" },
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
				route: "/desk/vetedge",
				edgeui_migrated: true,
				roles: [],
				badge: "",
			},
		],
	});

	const state = {
		installed: false,
		shellPatched: false,
		menuPatched: false,
		adapterPatched: false,
		notificationPatched: false,
		legacyClickBound: false,
		lifecycleBound: false,
		redirecting: false,
		lastError: null,
		routeItems: new Map(),
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

	function toDeskRoute(route) {
		const raw = String(route || "").trim();
		if (!raw) return "";
		try {
			const url = new URL(raw, window.location.origin);
			if (url.origin !== window.location.origin) return raw;
			if (url.pathname === "/app" || url.pathname.startsWith("/app/")) {
				url.pathname = `${DESK_PREFIX}${url.pathname.slice(4)}`;
			}
			if (!url.pathname.startsWith("/")) url.pathname = `/${url.pathname}`;
			return `${url.pathname}${url.search}${url.hash}`;
		} catch (_error) {
			const normalized = raw.replace(/^app\//, "").replace(/^desk\//, "").replace(/^\/+/, "");
			return `${DESK_PREFIX}/${normalized}`;
		}
	}

	function canonicalRoute(item) {
		const accepted = ACCEPTED_EDGEUI_ROUTES[routeKey(item)];
		if (accepted) return accepted;

		const supplied = String(item?.route || "").trim();
		if (supplied) return toDeskRoute(supplied);

		const target = String(item?.link_to || item?.linkTo || "").trim();
		if (!target) return "";
		const type = String(item?.link_type || item?.linkType || "Page");
		if (type === "Report") return `${DESK_PREFIX}/query-report/${encodeURIComponent(target)}`;
		if (type === "DocType") return `${DESK_PREFIX}/${slug(target)}`;
		return `${DESK_PREFIX}/${target.replace(/^\/+/, "")}`;
	}

	function routePath(route) {
		try {
			return new URL(toDeskRoute(route), window.location.origin).pathname.replace(/\/+$/, "") || DESK_PREFIX;
		} catch (_error) {
			return String(route || "").split("?")[0].replace(/\/+$/, "");
		}
	}

	function queryTarget(base, params) {
		const query = new URLSearchParams();
		Object.entries(params || {}).forEach(([key, value]) => {
			if (value !== undefined && value !== null && String(value) !== "") query.set(key, String(value));
		});
		const suffix = query.toString();
		return suffix ? `${base}?${suffix}` : base;
	}

	function isNewDocumentRoute(name, doctype = "") {
		const value = String(name || "").toLowerCase();
		const doctypeSlug = slug(doctype);
		return !value || value === "new" || (doctypeSlug && value.startsWith(`new-${doctypeSlug}`));
	}

	function acceptedTargetFromFrappeRoute() {
		let route = [];
		try {
			route = window.frappe?.get_route?.() || [];
		} catch (_error) {
			return "";
		}
		const routeType = String(route[0] || "");
		const doctype = String(route[1] || "");
		const name = route[2];

		if (doctype === "Veterinary Consultation") {
			if (routeType === "List") return "/desk/vetedge-clinical-workspace";
			if (routeType === "Form") {
				return isNewDocumentRoute(name, doctype)
					? "/desk/vetedge-clinical-workspace?new=1"
					: queryTarget("/desk/vetedge-clinical-workspace", { consultation: name });
			}
		}
		if (doctype === "Veterinary Settings" && ["List", "Form"].includes(routeType)) {
			return "/desk/veterinary-settings-center";
		}
		// Vital Signs intentionally remains a native DocType destination. Clinical
		// Workspace contains the accepted consultation-linked capture experience.
		if (doctype === "Veterinary Vital Signs") return "";

		const migrated = MIGRATED_DOCTYPES[doctype];
		if (migrated) {
			if (routeType === "List") return queryTarget(migrated.base, { resource: migrated.resource });
			if (routeType === "Form") {
				return isNewDocumentRoute(name, doctype)
					? queryTarget(migrated.base, { resource: migrated.resource, new: 1 })
					: queryTarget(migrated.base, { resource: migrated.resource, name });
			}
		}
		if (doctype === "Veterinary Guest Booking Request") {
			if (routeType === "List") return "/desk/vetedge-front-desk-action-center?tab=guest";
			if (routeType === "Form") return queryTarget("/desk/vetedge-front-desk-action-center", { tab: "guest", name });
		}
		if (doctype === "Veterinary Missed Appointment") {
			if (routeType === "List") return "/desk/vetedge-front-desk-action-center?tab=missed";
			if (routeType === "Form") return queryTarget("/desk/vetedge-front-desk-action-center", { tab: "missed", name });
		}
		if (routeType === "veterinary-appointment-queue") {
			return "/desk/vetedge-front-desk-action-center?tab=queue";
		}
		return "";
	}

	function rememberItem(item) {
		if (!item?.route) return item;
		state.routeItems.set(routePath(item.route), item);
		return item;
	}

	function normalizeItem(item) {
		const accepted = ACCEPTED_EDGEUI_ROUTES[routeKey(item)];
		return rememberItem({
			...item,
			link_type: item?.link_type || item?.linkType || "Page",
			link_to: item?.link_to || item?.linkTo || "",
			route: accepted || canonicalRoute(item),
			edgeui_migrated: Boolean(accepted || item?.edgeui_migrated),
		});
	}

	function hasHome(groups) {
		return (groups || []).some((group) =>
			(group.items || []).some((item) => item?.link_to === "vetedge" || routePath(item?.route) === "/desk/vetedge")
		);
	}

	function rewriteGroups(groups) {
		state.routeItems.clear();
		const rewritten = (Array.isArray(groups) ? groups : [])
			.map((group) => ({
				...group,
				items: (group.items || []).map(normalizeItem).filter((item) => item.label && item.route),
			}))
			.filter((group) => group.items.length);

		if (!hasHome(rewritten)) {
			const home = { ...HOME_GROUP, items: HOME_GROUP.items.map((item) => normalizeItem({ ...item })) };
			rewritten.unshift(home);
		}
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
			group.items.push(
				normalizeItem({
					label: source.label || source.link_to,
					icon: source.icon || "list",
					description: source.description || source.link_type || "Veterinary workspace",
					link_type: source.link_type || "Page",
					link_to: source.link_to || "",
					roles: Array.isArray(source.roles) ? source.roles : [],
					badge: source.badge || "",
				}),
			);
		}
		return rewriteGroups(groups);
	}

	function routeParts(url) {
		return url.pathname
			.replace(/^\/desk(?:\/|$)/, "")
			.split("/")
			.filter(Boolean)
			.map(decodeURIComponent);
	}

	function applyDeskRoute(target, itemOverride = null) {
		const route = toDeskRoute(target);
		if (!route) return false;

		try {
			const url = new URL(route, window.location.origin);
			if (url.origin !== window.location.origin || !/^\/desk(?:\/|$)/.test(url.pathname)) {
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

			const item = itemOverride || state.routeItems.get(routePath(route));
			if (item && !item.edgeui_migrated) {
				if (item.link_type === "Report" && item.link_to) {
					window.frappe.set_route("query-report", item.link_to);
					return true;
				}
				if (item.link_type === "DocType" && item.link_to) {
					window.frappe.set_route("List", item.link_to);
					return true;
				}
				if (item.link_type === "Page" && item.link_to) {
					window.frappe.set_route(item.link_to);
					return true;
				}
			}

			const parts = routeParts(url);
			if (!parts.length) return false;
			window.frappe.set_route(...parts);
			return true;
		} catch (error) {
			state.lastError = error?.message || String(error);
			window.location.assign(route);
			return true;
		}
	}

	function alignCurrentFrappeRoute() {
		if (state.redirecting) return false;
		const target = acceptedTargetFromFrappeRoute();
		if (!target) return false;
		const current = toDeskRoute(`${window.location.pathname}${window.location.search}`);
		if (current === target) return false;
		state.redirecting = true;
		try {
			return applyDeskRoute(target, { edgeui_migrated: true });
		} finally {
			window.setTimeout(() => {
				state.redirecting = false;
			}, 0);
		}
	}

	function installNavigationAdapters(edgeUI) {
		if (!edgeUI?.registerAdapter) return false;
		const adapter = {
			open(route) {
				return applyDeskRoute(route);
			},
		};
		edgeUI.registerAdapter("navigation:vetedge", adapter, { replace: true });
		edgeUI.registerAdapter("navigation:veterinary", adapter, { replace: true });
		state.adapterPatched = true;
		return true;
	}

	function installNotificationAdapter(edgeUI) {
		if (!edgeUI?.getAdapter || !edgeUI?.registerAdapter) return false;
		const current = edgeUI.getAdapter("notifications:vetedge") || edgeUI.getAdapter("notifications:veterinary");
		if (!current) return false;
		if (current.__vetedgeCanonicalDeskNotifications) {
			state.notificationPatched = true;
			return true;
		}
		const wrapped = {
			...current,
			__vetedgeCanonicalDeskNotifications: true,
			open(item) {
				const target = item?.target || item?.action_url || "";
				if (target && applyDeskRoute(target)) return true;
				return current.open?.(item) ?? false;
			},
		};
		edgeUI.registerAdapter("notifications:vetedge", wrapped, { replace: true });
		edgeUI.registerAdapter("notifications:veterinary", wrapped, { replace: true });
		state.notificationPatched = true;
		return true;
	}

	function installShellPatch(edgeUI) {
		if (edgeUI.__vetedgeCanonicalDeskNavigationShellInstalled) {
			state.shellPatched = true;
			return true;
		}
		const InnerShell = edgeUI.components?.EdgeAppShell;
		const Vue = edgeUI.Vue;
		if (!InnerShell || !Vue?.defineComponent || !Vue?.h || typeof edgeUI.registerComponent !== "function") return false;

		const CanonicalVetEdgeShell = Vue.defineComponent({
			name: "CanonicalVetEdgeDeskShell",
			inheritAttrs: false,
			setup(_props, context) {
				return () => {
					const attrs = context.attrs || {};
					const groups = rewriteGroups(
						Array.isArray(attrs.menuItems) && attrs.menuItems.length ? attrs.menuItems : groupsFromSidebar(),
					);
					return Vue.h(
						InnerShell,
						{
							...attrs,
							menuItems: groups,
							onNavigate: (route) => applyDeskRoute(route),
						},
						context.slots,
					);
				};
			},
		});

		edgeUI.registerComponent("EdgeAppShell", CanonicalVetEdgeShell, { replace: true });
		edgeUI.__vetedgeCanonicalDeskNavigationShellInstalled = true;
		state.shellPatched = true;
		return true;
	}

	function rewriteProductMenuConfig(config) {
		const product = String(config?.product || "").trim().toLowerCase();
		if (!PRODUCT_KEYS.has(product)) return config;

		const groups = rewriteGroups(
			(config.sections || []).map((section) => ({ ...section, items: section.items || [] })),
		);
		return {
			...config,
			sections: groups.map((group) => ({
				label: group.label,
				description: group.description || "",
				icon: group.icon || "layers",
				items: group.items.map((item) => ({ ...item, route: canonicalRoute(item) })),
			})),
			navigate(item) {
				const normalized = normalizeItem(item || {});
				return applyDeskRoute(normalized.route, normalized);
			},
		};
	}

	function installProductMenuPatch(edgeUI) {
		if (edgeUI.__vetedgeCanonicalDeskNavigationMenuPatched) {
			state.menuPatched = true;
			return true;
		}
		if (typeof edgeUI.registerProductMenu !== "function") return false;

		const previousRegister = edgeUI.registerProductMenu.bind(edgeUI);
		edgeUI.registerProductMenu = function registerCanonicalVetEdgeMenu(config) {
			return previousRegister(rewriteProductMenuConfig(config));
		};
		edgeUI.__vetedgeCanonicalDeskNavigationMenuPatched = true;
		state.menuPatched = true;

		const current = edgeUI.getProductMenuConfig?.();
		if (current && PRODUCT_KEYS.has(String(current.product || "").trim().toLowerCase())) {
			edgeUI.registerProductMenu(current);
			edgeUI.refreshProductMenu?.();
		}
		return true;
	}

	function bindLegacyAppClickCompatibility() {
		if (state.legacyClickBound) return;
		state.legacyClickBound = true;
		document.addEventListener(
			"click",
			(event) => {
				if (event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
				const anchor = event.target?.closest?.("a[href]");
				if (!anchor) return;
				try {
					const url = new URL(anchor.href, window.location.origin);
					if (url.origin !== window.location.origin || !(url.pathname === "/app" || url.pathname.startsWith("/app/"))) return;
					event.preventDefault();
					event.stopPropagation();
					applyDeskRoute(`${url.pathname}${url.search}${url.hash}`);
				} catch (_error) {
					// Leave malformed/external links to the browser.
				}
			},
			true,
		);
	}

	function install() {
		state.lastError = null;
		const edgeUI = runtime();
		if (!edgeUI) return false;
		try {
			groupsFromSidebar();
			installNavigationAdapters(edgeUI);
			installNotificationAdapter(edgeUI);
			installShellPatch(edgeUI);
			installProductMenuPatch(edgeUI);
			bindLegacyAppClickCompatibility();
			state.installed = state.adapterPatched && state.shellPatched && state.menuPatched;
			window.setTimeout(alignCurrentFrappeRoute, 0);
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
		window.frappe?.router?.on?.("change", () => {
			scheduleInstall();
			window.setTimeout(alignCurrentFrappeRoute, 0);
		});
	}

	function diagnose() {
		return {
			...state,
			homePresent: hasHome(groupsFromSidebar()),
			menuGroupCount: groupsFromSidebar().length,
			deskPrefix: DESK_PREFIX,
		};
	}

	window.VetEdgeNavigationRecovery = {
		install,
		diagnose,
		canonicalRoute,
		groupsFromSidebar,
		navigate: applyDeskRoute,
		toDeskRoute,
		alignCurrentFrappeRoute,
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
