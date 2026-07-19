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
		"/app/veterinary-patient": "patients",
		"/app/veterinary-appointment": "appointments",
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
	]);

	const state = {
		installed: false,
		lastError: null,
		runtimeVersion: "",
	};

	function runtime() {
		return window.EdgeSuiteUI || window.EdgeUI || null;
	}

	function call(method, args) {
		if (!window.frappe?.call) return Promise.reject(new Error("Frappe Desk is not ready."));
		return window.frappe.call(method, args || {});
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

	function openSameTab(route) {
		window.location.assign(route);
		return true;
	}

	function openNewTab(route) {
		window.open(route, "_blank", "noopener,noreferrer");
		return true;
	}

	function navigationAdapter() {
		return {
			open(route) {
				const path = normalizePath(route);
				if (!path) return false;

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
			const slug = String(item.reference_doctype)
				.trim()
				.toLowerCase()
				.replace(/[^a-z0-9]+/g, "-");
			return `/app/${slug}/${encodeURIComponent(item.reference_name)}`;
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
				return openNewTab(target);
			},
		};
	}

	function install() {
		state.lastError = null;
		const edgeUI = runtime();
		if (!edgeUI?.registerAdapter) return false;

		try {
			edgeUI.registerAdapter("navigation:vetedge", navigationAdapter(), { replace: true });
			edgeUI.registerAdapter("navigation:veterinary", navigationAdapter(), { replace: true });
			edgeUI.registerAdapter("notifications:vetedge", notificationAdapter(), { replace: true });
			edgeUI.registerAdapter("notifications:veterinary", notificationAdapter(), { replace: true });
			state.installed = true;
			state.runtimeVersion = edgeUI.version || "";
			return true;
		} catch (error) {
			state.lastError = error?.message || String(error);
			return false;
		}
	}

	function diagnose() {
		return {
			installed: state.installed,
			runtimeVersion: state.runtimeVersion,
			lastError: state.lastError,
			resourceRouteCount: Object.keys(RESOURCE_ROUTES).length,
		};
	}

	window.VetEdgeUIBridge = Object.assign(window.VetEdgeUIBridge || {}, {
		install,
		diagnose,
		resourceRoutes: RESOURCE_ROUTES,
	});

	if (!install()) {
		document.addEventListener("DOMContentLoaded", install, { once: true });
		window.setTimeout(install, 250);
		window.setTimeout(install, 1000);
	}
})();
