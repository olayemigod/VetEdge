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

	const DOCUMENT_ROUTES = Object.freeze({
		"/app/veterinary-patient": "patients",
		"/app/veterinary-appointment": "appointments",
		"/app/veterinary-settings": "settings",
	});

	const MASTER_ROUTES = Object.freeze({
		"/app/veterinary-species": "species",
		"/app/veterinary-breed": "breeds",
		"/app/veterinary-symptom": "symptoms",
		"/app/veterinary-diagnosis-category": "diagnosis-categories",
		"/app/veterinary-diagnosis": "diagnoses",
		"/app/veterinary-service-type": "service-types",
		"/app/consultation-type": "consultation-types",
	});

	// These records remain on the earlier read-focused Resource Center until their
	// complete EdgeSuite forms and workflow providers are migrated in later phases.
	const RESOURCE_ROUTES = Object.freeze({
		"/app/veterinary-missed-appointment": "missed-appointments",
		"/app/veterinary-consultation": "consultations",
		"/app/veterinary-lab-order": "lab-orders",
		"/app/veterinary-vaccination-record": "vaccinations",
		"/app/pet-grooming-appointment": "grooming",
		"/app/pet-boarding-booking": "boarding",
		"/app/kennel": "kennels",
	});

	const PRODUCT_ROUTES = new Set([
		"/app/vetedge-executive-dashboard",
		"/app/stock-expiry-monitor",
		"/app/vetedge-resource-center",
		"/app/vetedge-document-workspace",
		"/app/vetedge-master-workspace",
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
			return url.pathname.replace(/\/$/, "") || "/";
		} catch (_error) {
			return raw.split("?")[0].replace(/\/$/, "");
		}
	}

	function menuItemRoute(item) {
		if (item?.route) {
			const route = String(item.route).trim();
			if (!route) return "";
			if (route.startsWith("/")) return route;
			return `/app/${route.replace(/^\/+/, "")}`;
		}
		const target = String(item?.link_to || item?.linkTo || "").trim();
		if (!target) return "";
		const type = String(item?.link_type || item?.linkType || "Page");
		if (type === "Report") return `/app/query-report/${encodeURIComponent(target)}`;
		if (type === "DocType") return `/app/${slug(target)}`;
		return `/app/${target.replace(/^\/+/, "")}`;
	}

	function openSameTab(route) {
		window.location.assign(route);
		return true;
	}

	function openNewTab(route) {
		window.open(route, "_blank", "noopener,noreferrer");
		return true;
	}

	function migratedTarget(path, routes, workspacePath) {
		for (const [basePath, resource] of Object.entries(routes)) {
			if (path === basePath) {
				return `${workspacePath}?resource=${encodeURIComponent(resource)}`;
			}
			if (path.startsWith(`${basePath}/`)) {
				const name = decodeURIComponent(path.slice(basePath.length + 1));
				if (!name || resource === "settings") {
					return `${workspacePath}?resource=${encodeURIComponent(resource)}`;
				}
				return `${workspacePath}?resource=${encodeURIComponent(resource)}&name=${encodeURIComponent(name)}`;
			}
		}
		return "";
	}

	function migratedDocumentTarget(path) {
		return migratedTarget(path, DOCUMENT_ROUTES, "/app/vetedge-document-workspace");
	}

	function migratedMasterTarget(path) {
		return migratedTarget(path, MASTER_ROUTES, "/app/vetedge-master-workspace");
	}

	function navigationAdapter() {
		return {
			open(route) {
				const path = normalizePath(route);
				if (!path) return false;

				const migratedDocument = migratedDocumentTarget(path);
				if (migratedDocument) return openSameTab(migratedDocument);

				const migratedMaster = migratedMasterTarget(path);
				if (migratedMaster) return openSameTab(migratedMaster);

				const resource = RESOURCE_ROUTES[path];
				if (resource) {
					return openSameTab(`/app/vetedge-resource-center?resource=${encodeURIComponent(resource)}`);
				}

				if (PRODUCT_ROUTES.has(path)) return openSameTab(route);
				if (path.startsWith("/app/")) return openNewTab(route);
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
		if (item.action_url) return item.action_url;
		if (item.reference_doctype && item.reference_name) {
			const documentSlug = slug(item.reference_doctype);
			return `/app/${documentSlug}/${encodeURIComponent(item.reference_name)}`;
		}
		return item.name ? `/app/veterinary-notification-item/${encodeURIComponent(item.name)}` : "";
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
				if (navigationAdapter().open(target) === true) return true;
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
			documentRouteCount: Object.keys(DOCUMENT_ROUTES).length,
			masterRouteCount: Object.keys(MASTER_ROUTES).length,
			resourceRouteCount: Object.keys(RESOURCE_ROUTES).length,
		};
	}

	window.VetEdgeUIBridge = Object.assign(window.VetEdgeUIBridge || {}, {
		install,
		diagnose,
		documentRoutes: DOCUMENT_ROUTES,
		masterRoutes: MASTER_ROUTES,
		resourceRoutes: RESOURCE_ROUTES,
	});

	if (!install()) {
		document.addEventListener("DOMContentLoaded", install, { once: true });
		window.setTimeout(install, 250);
		window.setTimeout(install, 1000);
	}
})();
