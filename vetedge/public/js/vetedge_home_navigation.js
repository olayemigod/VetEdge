// Keep a stable Veterinary Home entry in the canonical VetEdge navigation.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const HOME_ROUTE = "/app/vetedge";
	const HOME_LABEL = "Veterinary Home";
	const LIFECYCLE_EVENTS = ["desktop_screen", "sidebar_setup", "toolbar_setup", "page-change"];

	function homeItem() {
		return {
			child: 1,
			collapsible: 0,
			icon: "home",
			indent: 0,
			keep_closed: 0,
			label: HOME_LABEL,
			link_to: "vetedge",
			link_type: "Page",
			route: HOME_ROUTE,
			show_arrow: 0,
			type: "Link",
		};
	}

	function dashboardSection() {
		return {
			child: 0,
			collapsible: 1,
			indent: 1,
			keep_closed: 0,
			label: "Dashboard",
			link_type: "DocType",
			show_arrow: 0,
			type: "Section Break",
		};
	}

	function canonicalSidebar() {
		const boot = window.frappe?.boot;
		if (!boot) return null;
		boot.workspace_sidebar_item = boot.workspace_sidebar_item || {};
		const existing = boot.workspace_sidebar_item.veterinary || boot.workspace_sidebar_item.vetedge;
		if (existing) return existing;
		const created = { items: [dashboardSection()] };
		boot.workspace_sidebar_item.veterinary = created;
		boot.workspace_sidebar_item.vetedge = created;
		return created;
	}

	function itemRoute(item) {
		const direct = String(item?.route || "").trim();
		if (direct) return direct.replace(/\/$/, "");
		const target = String(item?.link_to || "").trim().toLowerCase();
		return item?.link_type === "Page" && target === "vetedge" ? HOME_ROUTE : "";
	}

	function ensureHomeLink() {
		const sidebar = canonicalSidebar();
		if (!sidebar) return false;
		sidebar.items = Array.isArray(sidebar.items) ? sidebar.items : [];
		const exists = sidebar.items.some(
			(item) => item?.label === HOME_LABEL || itemRoute(item) === HOME_ROUTE,
		);
		if (exists) return true;

		let insertAt = sidebar.items.findIndex(
			(item) => item?.type === "Section Break" && String(item?.label || "").trim() === "Dashboard",
		);
		if (insertAt < 0) {
			sidebar.items.unshift(dashboardSection());
			insertAt = 0;
		}
		sidebar.items.splice(insertAt + 1, 0, homeItem());
		return true;
	}

	function install() {
		const installed = ensureHomeLink();
		if (installed) {
			window.VetEdgeProfessionalUI?.install?.();
		}
		return installed;
	}

	window.VetEdgeHomeNavigation = Object.assign(window.VetEdgeHomeNavigation || {}, {
		install,
		ensureHomeLink,
		homeRoute: HOME_ROUTE,
	});

	install();
	LIFECYCLE_EVENTS.forEach((eventName) => document.addEventListener(eventName, install));
	window.frappe?.router?.on?.("change", install);
})();
