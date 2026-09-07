// VetEdge waffle/Product Menu navigation hardening.
//
// The shared Product Menu can be rendered/re-rendered by EdgeSuite UI while a
// previous Desk page still owns query state. Product Menu destinations must be
// resolved from the clicked menu item itself and must replace the current URL
// completely; stale route_options or a previous ?name=... must never be reused
// as the identifier for the next DocType/workspace.
(function installVetEdgeWaffleNavigationHardening(global) {
	"use strict";

	if (!global || global.__vetedgeWaffleNavigationHardeningInstalled) return;
	global.__vetedgeWaffleNavigationHardeningInstalled = true;

	const PANEL_SELECTOR = "#edge-product-menu-dropdown, #vetedge-product-menu-panel";
	const INTERACTIVE_SELECTOR = "button, a, [role='menuitem'], [data-link-to], [data-route]";
	const KNOWN_ROUTES = Object.freeze({
		"Veterinary Patient": "/desk/vetedge-resource-center?resource=patients",
		"Veterinary Appointment": "/desk/vetedge-resource-center?resource=appointments",
		"Veterinary Consultation": "/desk/vetedge-clinical-workspace",
		"Veterinary Guest Booking Request": "/desk/vetedge-front-desk-action-center?tab=guest",
		"Veterinary Missed Appointment": "/desk/vetedge-front-desk-action-center?tab=missed",
		"Veterinary Billing Session": "/desk/vetedge-billing-sessions",
		"vetedge-billing-center": "/desk/vetedge-billing-center",
		"vetedge-billing-sessions": "/desk/vetedge-billing-sessions",
	});

	function runtime() {
		return global.EdgeSuiteUI || global.EdgeUI || null;
	}

	function normalize(value) {
		return String(value || "").replace(/\s+/g, " ").trim();
	}

	function slug(value) {
		return normalize(value)
			.toLowerCase()
			.replace(/[^a-z0-9]+/g, "-")
			.replace(/^-|-$/g, "");
	}

	function sidebarItems() {
		const sidebar = global.frappe?.boot?.workspace_sidebar_item;
		const source = sidebar && (sidebar.vetedge || sidebar.veterinary);
		return (source?.items || [])
			.filter((item) => item?.type === "Link" && item?.hidden !== 1)
			.map((item) => ({
				label: item.label,
				link_type: item.link_type,
				link_to: item.link_to,
				route: item.route || "",
			}));
	}

	function configuredItems() {
		try {
			const sections = runtime()?.getProductMenuConfig?.()?.sections || [];
			const configured = sections.flatMap((section) => section?.items || []);
			if (configured.length) return configured;
		} catch (_error) {
			// Fall back to the permission-filtered VetEdge workspace sidebar below.
		}
		return sidebarItems();
	}

	function explicitItem(node) {
		if (!node) return {};
		return {
			label: normalize(node.dataset?.label || node.getAttribute?.("aria-label")),
			link_type: normalize(node.dataset?.linkType || node.getAttribute?.("data-link-type")),
			link_to: normalize(node.dataset?.linkTo || node.getAttribute?.("data-link-to")),
			route: normalize(node.dataset?.route || node.getAttribute?.("data-route") || node.getAttribute?.("href")),
		};
	}

	function itemForNode(node) {
		const explicit = explicitItem(node);
		const text = normalize(node?.textContent).toLowerCase();
		const candidates = configuredItems()
			.filter((item) => normalize(item?.label))
			.sort((left, right) => normalize(right?.label).length - normalize(left?.label).length);

		let configured = null;
		if (explicit.link_to) {
			configured = candidates.find((item) => normalize(item?.link_to || item?.linkTo) === explicit.link_to) || null;
		}
		if (!configured && explicit.label) {
			const label = explicit.label.toLowerCase();
			configured = candidates.find((item) => normalize(item?.label).toLowerCase() === label) || null;
		}
		if (!configured && text) {
			configured = candidates.find((item) => {
				const label = normalize(item?.label).toLowerCase();
				return text === label || text.startsWith(`${label} `) || text.includes(label);
			}) || null;
		}

		if (!configured && !explicit.link_to && !explicit.route) return null;
		configured = configured || {};
		return {
			label: configured.label || explicit.label,
			link_type: explicit.link_type || configured.link_type || configured.linkType || "Page",
			link_to: explicit.link_to || configured.link_to || configured.linkTo || "",
			route: explicit.route || configured.route || "",
		};
	}

	function canonicalRoute(item) {
		const linkTo = normalize(item?.link_to || item?.linkTo);
		if (KNOWN_ROUTES[linkTo]) return KNOWN_ROUTES[linkTo];

		const label = normalize(item?.label);
		if (label === "Patients") return KNOWN_ROUTES["Veterinary Patient"];
		if (label === "Appointments") return KNOWN_ROUTES["Veterinary Appointment"];
		if (label === "Billing Center") return KNOWN_ROUTES["vetedge-billing-center"];
		if (label === "Billing Session" || label === "Billing Sessions") return KNOWN_ROUTES["vetedge-billing-sessions"];

		try {
			const recovered = global.VetEdgeNavigationRecovery?.canonicalRoute?.(item);
			if (recovered) return recovered;
		} catch (_error) {
			// Use the deterministic item route/native fallback below.
		}

		const supplied = normalize(item?.route);
		if (supplied && supplied !== "#") return supplied;
		if (!linkTo) return "";
		const type = normalize(item?.link_type || item?.linkType || "Page");
		if (type === "Report") return `/desk/query-report/${encodeURIComponent(linkTo)}`;
		if (type === "DocType") return `/desk/${slug(linkTo)}`;
		return `/desk/${linkTo.replace(/^\/+/, "")}`;
	}

	function sameWindow(route) {
		const target = normalize(route);
		if (!target) return false;
		let url;
		try {
			url = new URL(target, global.location.origin);
		} catch (_error) {
			return false;
		}
		if (url.origin !== global.location.origin) return false;
		if (url.pathname === "/app" || url.pathname.startsWith("/app/")) {
			url.pathname = `/desk${url.pathname.slice(4)}`;
		}

		// Frappe route_options is intentionally one-shot state. A stale value from
		// the previous document must not become the identifier/filter of the next
		// Product Menu destination.
		if (global.frappe) global.frappe.route_options = null;

		const next = `${url.pathname}${url.search}${url.hash}`;
		const current = `${global.location.pathname}${global.location.search}${global.location.hash}`;
		if (next === current) return true;
		global.location.assign(next);
		return true;
	}

	function productMenuClick(event) {
		const panel = event.target?.closest?.(PANEL_SELECTOR);
		if (!panel) return;
		if (event.target?.closest?.("input, textarea, select, option")) return;
		if (event.target?.closest?.(".edge-product-menu__close, [data-action='close'], [aria-label*='Close']")) return;

		const node = event.target?.closest?.(INTERACTIVE_SELECTOR);
		if (!node || !panel.contains(node)) return;
		const item = itemForNode(node);
		if (!item) return;
		const route = canonicalRoute(item);
		if (!route) return;

		event.preventDefault();
		event.stopPropagation();
		event.stopImmediatePropagation();
		try { runtime()?.closeProductMenu?.(); } catch (_error) { /* no-op */ }
		const fallback = global.document?.querySelector?.("#vetedge-product-menu-panel");
		if (fallback) fallback.hidden = true;
		sameWindow(route);
	}

	global.document?.addEventListener("click", productMenuClick, true);

	global.VetEdgeWaffleNavigationHardening = Object.freeze({
		canonicalRoute,
		itemForNode,
		sameWindow,
		reconcile() {
			if (global.frappe?.route_options && !global.document?.querySelector?.(PANEL_SELECTOR)) return false;
			return true;
		},
	});
})(window);
