(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const API = Object.freeze({
		count: "vetedge.services.notification_api.get_my_veterinary_unread_bell_count",
		feed: "vetedge.services.notification_api.get_my_notifications",
		mark_all: "vetedge.services.notification_api.mark_all_my_veterinary_notifications_read",
		read: "vetedge.services.notification_api.mark_my_notification_read",
		acknowledge: "vetedge.services.notification_api.acknowledge_my_notification",
		done: "vetedge.services.notification_api.mark_my_notification_done",
		dismiss: "vetedge.services.notification_api.dismiss_my_notification",
		archive: "vetedge.services.notification_api.archive_my_notification",
	});

	const RESOURCE_ROUTES = Object.freeze({
		"/desk/veterinary-patient": "patients",
		"/desk/veterinary-appointment": "appointments",
		"/desk/veterinary-lab-order": "lab-orders",
		"/desk/veterinary-vaccination-record": "vaccinations",
		"/desk/pet-grooming-appointment": "grooming",
		"/desk/pet-boarding-booking": "boarding",
		"/desk/kennel": "kennels",
	});

	const MASTER_ROUTES = Object.freeze({
		"/desk/veterinary-species": "species",
		"/desk/veterinary-breed": "breeds",
		"/desk/veterinary-symptom": "symptoms",
		"/desk/veterinary-diagnosis-category": "diagnosis-categories",
		"/desk/veterinary-diagnosis": "diagnoses",
		"/desk/veterinary-service-type": "service-types",
		"/desk/consultation-type": "consultation-types",
	});

	const PRICING_ROUTES = Object.freeze({
		"/desk/veterinary-treatment-item": "treatment-items",
		"/desk/veterinary-treatment-type": "treatment-types",
		"/desk/veterinary-lab-test": "lab-tests",
		"/desk/veterinary-vaccine": "vaccines",
		"/desk/pet-grooming-service": "grooming-services",
	});

	const SERVICE_ROUTES = Object.freeze({
		"/desk/pet-boarding-stay": "boarding-stays",
		"/desk/pet-boarding-care-record": "boarding-care-records",
		"/desk/pet-grooming-session": "grooming-sessions",
	});

	const SERVICE_PAGES = Object.freeze({
		"/desk/kennel-availability": "availability",
		"/desk/kennel-availability-board": "availability",
	});

	const PRODUCT_ROUTES = new Set([
		"/desk/vetedge",
		"/desk/vetedge-executive-dashboard",
		"/desk/stock-expiry-monitor",
		"/desk/vetedge-resource-center",
		"/desk/veterinary-settings-center",
		"/desk/vetedge-master-workspace",
		"/desk/vetedge-pricing-master-workspace",
		"/desk/vetedge-front-desk-action-center",
		"/desk/vetedge-clinical-workspace",
		"/desk/veterinary-medical-history",
		"/desk/vetedge-service-operations",
	]);

	const FRONT_DESK_FOCUS = Object.freeze({
		queue: { section: "Front Desk", items: ["Appointment Queue"] },
		guest: { section: "Front Desk", items: ["Guest Booking Requests"] },
		missed: { section: "Front Desk", items: ["Missed Appointments"] },
	});

	const RESOURCE_FOCUS = Object.freeze({
		patients: { section: "Front Desk", items: ["Patients"] },
		appointments: { section: "Front Desk", items: ["Appointments"] },
		"missed-appointments": { section: "Front Desk", items: ["Missed Appointments"] },
		consultations: { section: "Clinical", items: ["Consultations"] },
		"lab-orders": { section: "Clinical", items: ["Lab Orders", "Laboratory Orders"] },
		vaccinations: { section: "Clinical", items: ["Vaccination Records", "Vaccinations"] },
		boarding: { section: "Hospital & Services", items: ["Pet Boarding Booking"] },
		grooming: { section: "Hospital & Services", items: ["Pet Grooming Appointment"] },
		kennels: { section: "Hospital & Services", items: ["Kennel Availability Board", "Kennels"] },
	});

	const SERVICE_FOCUS = Object.freeze({
		availability: { section: "Hospital & Services", items: ["Kennel Availability Board"] },
		"boarding-stays": { section: "Hospital & Services", items: ["Pet Boarding Stay"] },
		"boarding-care-records": { section: "Hospital & Services", items: ["Pet Boarding Care Record"] },
		"grooming-sessions": { section: "Hospital & Services", items: ["Pet Grooming Session"] },
	});

	const PATH_FOCUS = Object.freeze({
		"/desk/vetedge-clinical-workspace": { section: "Clinical", items: ["Consultations"] },
		"/desk/veterinary-medical-history": { section: "Clinical", items: ["Medical History"] },
	});

	const state = {
		installed: false,
		lastError: null,
		runtimeVersion: "",
		productMenuPatched: false,
		sidebarFocusInstalled: false,
		sidebarFocusTarget: "",
		sidebarFocusObserver: null,
		sidebarFocusScheduled: false,
		historyFocusPatched: false,
	};

	function runtime() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	}

	function supportsSharedContracts(version) {
		const parts = String(version || "0.0.0")
			.split(".")
			.map((value) => Number.parseInt(value, 10) || 0);
		return parts[0] > 0 || (parts[0] === 0 && parts[1] >= 3);
	}

	function call(method, args) {
		if (!window.frappe?.call) return Promise.reject(new Error("Frappe Desk is not ready."));
		return window.frappe.call(method, args || {});
	}

	function slug(value) {
		return String(value || "")
			.trim()
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, "-")
			.replace(/^-|-$/g, "");
	}

	function normalizePath(route) {
		const raw = String(route || "").trim();
		if (!raw) return "";
		try {
			const url = new URL(raw, window.location.origin);
			let path = url.pathname.replace(/\/$/, "") || "/";
			if (path === "/app" || path.startsWith("/app/")) path = `/desk${path.slice(4)}`;
			return path;
		} catch (_error) {
			let path = raw.split("?")[0].replace(/\/$/, "");
			if (path === "/app" || path.startsWith("/app/")) path = `/desk${path.slice(4)}`;
			return path;
		}
	}

	function deskRoute(route) {
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

	function menuItemRoute(item) {
		if (item?.route) {
			const route = String(item.route).trim();
			if (!route) return "";
			if (route.startsWith("/")) return deskRoute(route);
			return `/desk/${route.replace(/^\/+/, "")}`;
		}
		const target = String(item?.link_to || item?.linkTo || "").trim();
		if (!target) return "";
		const type = String(item?.link_type || item?.linkType || "Page");
		if (type === "Report") return `/desk/query-report/${encodeURIComponent(target)}`;
		if (type === "DocType") return `/desk/${slug(target)}`;
		return `/desk/${target.replace(/^\/+/, "")}`;
	}

	function openSameTab(route) {
		window.location.assign(deskRoute(route));
		return true;
	}

	function openNewTab(route) {
		window.open(deskRoute(route), "_blank", "noopener,noreferrer");
		return true;
	}

	function migratedTarget(path, routes, workspacePath) {
		for (const [basePath, resource] of Object.entries(routes)) {
			if (path === basePath) {
				return `${workspacePath}?resource=${encodeURIComponent(resource)}`;
			}
			if (path.startsWith(`${basePath}/`)) {
				const name = decodeURIComponent(path.slice(basePath.length + 1));
				if (!name) return `${workspacePath}?resource=${encodeURIComponent(resource)}`;
				return `${workspacePath}?resource=${encodeURIComponent(resource)}&name=${encodeURIComponent(name)}`;
			}
		}
		return "";
	}

	function serviceTarget(path) {
		const pageResource = SERVICE_PAGES[path];
		if (pageResource) return `/desk/vetedge-service-operations?resource=${encodeURIComponent(pageResource)}`;
		return migratedTarget(path, SERVICE_ROUTES, "/desk/vetedge-service-operations");
	}

	function clinicalTarget(path) {
		const base = "/desk/veterinary-consultation";
		if (path === base) return "/desk/vetedge-clinical-workspace";
		if (!path.startsWith(`${base}/`)) return "";
		const name = decodeURIComponent(path.slice(base.length + 1));
		if (!name || name === "new" || name.toLowerCase().startsWith("new-veterinary-consultation")) {
			return "/desk/vetedge-clinical-workspace?new=1";
		}
		return `/desk/vetedge-clinical-workspace?consultation=${encodeURIComponent(name)}`;
	}

	function frontDeskTarget(path) {
		const routes = [
			["/desk/veterinary-guest-booking-request", "guest"],
			["/desk/veterinary-missed-appointment", "missed"],
		];
		for (const [base, tab] of routes) {
			if (path === base) return `/desk/vetedge-front-desk-action-center?tab=${tab}`;
			if (path.startsWith(`${base}/`)) {
				const name = decodeURIComponent(path.slice(base.length + 1));
				return `/desk/vetedge-front-desk-action-center?tab=${tab}${name ? `&name=${encodeURIComponent(name)}` : ""}`;
			}
		}
		if (path === "/desk/veterinary-appointment-queue") {
			return "/desk/vetedge-front-desk-action-center?tab=queue";
		}
		return "";
	}

	function navigationAdapter() {
		return {
			open(route) {
				const path = normalizePath(route);
				if (!path) return false;

				if (path === "/desk/veterinary-settings") {
					return openSameTab("/desk/veterinary-settings-center");
				}

				if (path === "/desk/veterinary-vital-signs" || path.startsWith("/desk/veterinary-vital-signs/")) {
					return openSameTab(route);
				}

				const service = serviceTarget(path);
				if (service) return openSameTab(service);

				const clinical = clinicalTarget(path);
				if (clinical) return openSameTab(clinical);

				const frontDesk = frontDeskTarget(path);
				if (frontDesk) return openSameTab(frontDesk);

				const migratedMaster = migratedTarget(path, MASTER_ROUTES, "/desk/vetedge-master-workspace");
				if (migratedMaster) return openSameTab(migratedMaster);

				const migratedPricing = migratedTarget(path, PRICING_ROUTES, "/desk/vetedge-pricing-master-workspace");
				if (migratedPricing) return openSameTab(migratedPricing);

				const resource = RESOURCE_ROUTES[path];
				if (resource) {
					return openSameTab(`/desk/vetedge-resource-center?resource=${encodeURIComponent(resource)}`);
				}

				if (PRODUCT_ROUTES.has(path)) return openSameTab(route);
				if (path.startsWith("/desk/")) return openNewTab(route);
				return false;
			},
		};
	}

	function patchProductMenu(edgeUI, adapter) {
		if (edgeUI.__vetedgeProductMenuNavigationPatched) {
			state.productMenuPatched = true;
			return;
		}
		if (typeof edgeUI.registerProductMenu !== "function") return;

		const originalRegister = edgeUI.registerProductMenu.bind(edgeUI);
		edgeUI.registerProductMenu = function (config) {
			const product = String(config?.product || "").trim().toLowerCase();
			if (!["vetedge", "veterinary"].includes(product)) {
				return originalRegister(config);
			}

			const suppliedNavigate = typeof config.navigate === "function" ? config.navigate : null;
			return originalRegister({
				...config,
				navigate(item) {
					const route = menuItemRoute(item);
					if (route && adapter.open(route) === true) return;
					if (suppliedNavigate) {
						suppliedNavigate(item);
						return;
					}
					if (route) openSameTab(route);
				},
			});
		};

		edgeUI.__vetedgeProductMenuNavigationPatched = true;
		state.productMenuPatched = true;
		const currentConfig = edgeUI.getProductMenuConfig?.();
		if (currentConfig) edgeUI.registerProductMenu(currentConfig);
	}

	function sectionLabel(section) {
		const toggle = section?.querySelector?.(".edge-sidebar__section-toggle");
		if (!toggle) return "";
		const children = [...toggle.children];
		const labelNode = children.find((node) => !node.classList?.contains("edge-icon"));
		return String(labelNode?.textContent || toggle.textContent || "").trim();
	}

	function itemLabel(item) {
		return String(item?.querySelector?.(".edge-sidebar-item__label")?.textContent || "").trim();
	}

	function currentSidebarFocus() {
		const path = normalizePath(`${window.location.pathname}${window.location.search}`);
		const params = new URLSearchParams(window.location.search || "");

		if (path === "/desk/vetedge-front-desk-action-center") {
			return FRONT_DESK_FOCUS[params.get("tab") || "queue"] || FRONT_DESK_FOCUS.queue;
		}
		if (path === "/desk/vetedge-resource-center") {
			return RESOURCE_FOCUS[params.get("resource") || "patients"] || null;
		}
		if (path === "/desk/vetedge-service-operations") {
			return SERVICE_FOCUS[params.get("resource") || ""] || null;
		}
		return PATH_FOCUS[path] || null;
	}

	function findSidebarTarget(shell, focus) {
		if (!shell || !focus) return null;
		const section = [...shell.querySelectorAll(".edge-sidebar__section")].find(
			(candidate) => sectionLabel(candidate) === focus.section,
		);
		if (!section) return null;
		const wanted = new Set((focus.items || []).map((label) => String(label).trim()));
		const item = [...section.querySelectorAll(".edge-sidebar-item")].find((candidate) =>
			wanted.has(itemLabel(candidate)),
		);
		return item ? { section, item } : null;
	}

	function collapseOtherSidebarSections(shell, activeSection) {
		shell.querySelectorAll(".edge-sidebar__section").forEach((section) => {
			if (section === activeSection) return;
			const toggle = section.querySelector(".edge-sidebar__section-toggle");
			if (toggle?.getAttribute("aria-expanded") === "true") toggle.click();
		});
	}

	function syncSidebarFocus() {
		state.sidebarFocusScheduled = false;
		const focus = currentSidebarFocus();
		state.sidebarFocusTarget = focus ? `${focus.section}/${focus.items?.[0] || ""}` : "";
		if (!focus) return false;

		let applied = false;
		document
			.querySelectorAll(
				".edge-app-shell[data-edge-product='vetedge'], .edge-app-shell[data-edge-product='veterinary']",
			)
			.forEach((shell) => {
				const target = findSidebarTarget(shell, focus);
				if (!target) return;
				applied = true;

				shell.querySelectorAll(".edge-sidebar-item").forEach((item) => {
					const active = item === target.item;
					if (item.classList.contains("active") !== active) item.classList.toggle("active", active);
					if (active) {
						if (item.getAttribute("aria-current") !== "page") item.setAttribute("aria-current", "page");
					} else if (item.hasAttribute("aria-current")) {
						item.removeAttribute("aria-current");
					}
				});

				if (shell.classList.contains("edge-nav-shell--collapsed")) return;
				const activeToggle = target.section.querySelector(".edge-sidebar__section-toggle");
				if (activeToggle?.getAttribute("aria-expanded") !== "true") activeToggle?.click();
				window.setTimeout(() => {
					collapseOtherSidebarSections(shell, target.section);
					window.EdgeSuiteNavigation?.syncActiveSection?.(shell);
				}, 0);
			});
		return applied;
	}

	function scheduleSidebarFocus() {
		if (state.sidebarFocusScheduled) return;
		state.sidebarFocusScheduled = true;
		window.setTimeout(syncSidebarFocus, 0);
	}

	function patchHistoryForSidebarFocus() {
		if (state.historyFocusPatched || !window.history) return;
		state.historyFocusPatched = true;
		for (const methodName of ["pushState", "replaceState"]) {
			const original = window.history[methodName];
			if (typeof original !== "function" || original.__vetedgeSidebarFocusPatched) continue;
			const wrapped = function (...args) {
				const result = original.apply(this, args);
				scheduleSidebarFocus();
				return result;
			};
			wrapped.__vetedgeSidebarFocusPatched = true;
			window.history[methodName] = wrapped;
		}
		window.addEventListener("popstate", scheduleSidebarFocus);
	}

	function installSidebarFocus() {
		if (typeof document === "undefined") return false;
		patchHistoryForSidebarFocus();
		if (!state.sidebarFocusInstalled) {
			state.sidebarFocusInstalled = true;
			for (const eventName of ["page-change", "desktop_screen", "sidebar_setup", "toolbar_setup"]) {
				document.addEventListener(eventName, scheduleSidebarFocus);
			}
			if (window.MutationObserver && document.body) {
				state.sidebarFocusObserver = new MutationObserver((records) => {
					const relevant = records.some((record) => {
						if (record.type === "attributes") {
							return record.target?.matches?.(".edge-sidebar-item");
						}
						return [...(record.addedNodes || [])].some(
							(node) =>
								node.nodeType === 1 &&
								(node.matches?.(".edge-app-shell, .edge-sidebar") ||
									node.querySelector?.(".edge-app-shell, .edge-sidebar")),
						);
					});
					if (relevant) scheduleSidebarFocus();
				});
				state.sidebarFocusObserver.observe(document.body, {
					childList: true,
					subtree: true,
					attributes: true,
					attributeFilter: ["class", "aria-current"],
				});
			}
		}
		scheduleSidebarFocus();
		window.setTimeout(syncSidebarFocus, 80);
		window.setTimeout(syncSidebarFocus, 250);
		return true;
	}

	function notificationActions(item) {
		const status = item.status || "Unread";
		return [
			item.action_url || item.reference_doctype || item.reference_name
				? { key: "open", label: "Open", primary: true }
				: null,
			status === "Unread" ? { key: "read", label: "Mark read" } : null,
			status !== "Acknowledged" ? { key: "acknowledge", label: "Acknowledge" } : null,
			{ key: "done", label: "Done" },
			{ key: "dismiss", label: "Dismiss" },
			{ key: "archive", label: "Archive" },
		].filter(Boolean);
	}

	function targetForItem(item) {
		if (item.action_url) return deskRoute(item.action_url);
		if (item.reference_doctype && item.reference_name) {
			const documentSlug = slug(item.reference_doctype);
			return `/desk/${documentSlug}/${encodeURIComponent(item.reference_name)}`;
		}
		return item.name ? `/desk/veterinary-notification-item/${encodeURIComponent(item.name)}` : "";
	}

	function normalizeNotification(item) {
		return {
			...item,
			id: item.name,
			title: item.title || "Notification",
			message: item.message || "",
			status: item.status || "Unread",
			category: item.category || item.priority || "Veterinary",
			created_at: item.creation || "",
			unread: (item.status || "Unread") === "Unread",
			target: targetForItem(item),
			actions: notificationActions(item),
		};
	}

	function notificationAdapter() {
		return {
			async getCount() {
				const response = await call(API.count);
				return Number(response?.message?.unread_count || 0);
			},

			async getItems({ limit = 24 } = {}) {
				const response = await call(API.feed, { limit });
				return (response?.message?.items || []).map(normalizeNotification);
			},

			async markAllRead() {
				await call(API.mark_all);
			},

			async performAction(action, item) {
				if (action === "open") return { refresh: false };
				const method = API[action];
				if (!method || !item?.name) return { refresh: false };
				await call(method, { notification_name: item.name });
				return {
					refresh: true,
					remove: ["done", "dismiss", "archive"].includes(action),
				};
			},

			open(item) {
				const target = item?.target || targetForItem(item || {});
				if (!target) return false;
				const navigation = navigationAdapter();
				if (navigation.open(target) === true) return true;
				return openNewTab(target);
			},
		};
	}

	function install() {
		state.lastError = null;
		installSidebarFocus();
		const edgeUI = runtime();
		state.runtimeVersion = edgeUI?.version || "";
		if (!edgeUI?.registerAdapter) return false;
		if (!supportsSharedContracts(edgeUI.version)) {
			state.installed = false;
			state.lastError = `VetEdge requires EdgeSuite UI 0.3 or newer; found ${edgeUI.version || "unknown"}.`;
			return false;
		}

		try {
			const navigation = navigationAdapter();
			edgeUI.registerAdapter("navigation:vetedge", navigation, { replace: true });
			edgeUI.registerAdapter("navigation:veterinary", navigation, { replace: true });
			edgeUI.registerAdapter("notifications:vetedge", notificationAdapter(), { replace: true });
			edgeUI.registerAdapter("notifications:veterinary", notificationAdapter(), { replace: true });
			patchProductMenu(edgeUI, navigation);
			state.installed = true;
			state.runtimeVersion = edgeUI.version || "";
			scheduleSidebarFocus();
			return true;
		} catch (error) {
			state.installed = false;
			state.lastError = error?.message || String(error);
			return false;
		}
	}

	function diagnose() {
		return {
			installed: state.installed,
			runtimeVersion: state.runtimeVersion,
			lastError: state.lastError,
			productMenuPatched: state.productMenuPatched,
			sidebarFocusInstalled: state.sidebarFocusInstalled,
			sidebarFocusTarget: state.sidebarFocusTarget,
			resourceRouteCount: Object.keys(RESOURCE_ROUTES).length,
			masterRouteCount: Object.keys(MASTER_ROUTES).length,
			pricingRouteCount: Object.keys(PRICING_ROUTES).length,
			serviceRouteCount: Object.keys(SERVICE_ROUTES).length + Object.keys(SERVICE_PAGES).length,
		};
	}

	window.VetEdgeUIBridge = Object.assign(window.VetEdgeUIBridge || {}, {
		install,
		diagnose,
		resolveSidebarFocus: currentSidebarFocus,
		syncSidebarFocus,
		resourceRoutes: RESOURCE_ROUTES,
		masterRoutes: MASTER_ROUTES,
		pricingRoutes: PRICING_ROUTES,
		serviceRoutes: SERVICE_ROUTES,
	});

	if (!install()) {
		document.addEventListener("DOMContentLoaded", install, { once: true });
		window.setTimeout(install, 250);
		window.setTimeout(install, 1000);
	}
})();