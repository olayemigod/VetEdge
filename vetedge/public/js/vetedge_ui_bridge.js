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

	const state = {
		installed: false,
		lastError: null,
		runtimeVersion: "",
		productMenuPatched: false,
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
			resourceRouteCount: Object.keys(RESOURCE_ROUTES).length,
			masterRouteCount: Object.keys(MASTER_ROUTES).length,
			pricingRouteCount: Object.keys(PRICING_ROUTES).length,
			serviceRouteCount: Object.keys(SERVICE_ROUTES).length + Object.keys(SERVICE_PAGES).length,
		};
	}

	window.VetEdgeUIBridge = Object.assign(window.VetEdgeUIBridge || {}, {
		install,
		diagnose,
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