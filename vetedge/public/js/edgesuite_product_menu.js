// VetEdge Product Menu: canonical Workspace Sidebar rendered through EdgeSuite UI or a safe Desk fallback.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const PRODUCT = "VetEdge";
	const EDGE_TRIGGER = "edge-product-menu-trigger";
	const FALLBACK_SLOT = "vetedge-product-menu-slot";
	const FALLBACK_TRIGGER = "vetedge-product-menu-trigger";
	const FALLBACK_PANEL = "vetedge-product-menu-panel";
	const NAVBAR_TARGET_SELECTORS = [
		"header .navbar .navbar-right",
		".navbar .navbar-right",
		"header .navbar .navbar-nav.ms-auto",
		"header .navbar .navbar-nav.ml-auto",
		"header .navbar .navbar-nav",
	];
	const LIFECYCLE_EVENTS = ["toolbar_setup", "page-change", "desktop_screen", "sidebar_setup"];
	let fallbackEventsBound = false;
	let lifecycleEventsBound = false;
	let observer;
	let scheduledMount;

	function canonicalSidebar() {
		const sidebars = window.frappe?.boot?.workspace_sidebar_item;
		return sidebars && (sidebars.vetedge || sidebars.veterinary);
	}

	function normalizeItem(item) {
		return {
			label: item.label,
			icon: item.icon || "list",
			link_type: item.link_type,
			link_to: item.link_to,
			route: item.route || "",
			display_depends_on: item.display_depends_on || "",
			roles: item.roles || [],
			feature_key: item.feature_key || "",
			visible: item.hidden !== 1,
		};
	}

	function normalizeSections() {
		const sections = [];
		let section;
		((canonicalSidebar() || {}).items || []).forEach((item) => {
			if (item.type === "Section Break") {
				section = {
					label: item.label,
					icon: item.icon || "",
					collapsible: Boolean(item.collapsible),
					keep_closed: Boolean(item.keep_closed),
					items: [],
				};
				sections.push(section);
			} else if (item.type === "Link" && section) {
				section.items.push(normalizeItem(item));
			}
		});
		return sections.filter((item) => item.items.length);
	}

	function profile() {
		const boot = window.frappe?.boot || {};
		const user = window.frappe?.session?.user || boot.user?.name || "";
		return {
			name: boot.user?.full_name || boot.user?.name || user || "Veterinary User",
			email: user,
			company: boot.sysdefaults?.company || "",
			branch: boot.edgesuite_product_menu?.branch || "",
		};
	}

	function currentRoute() {
		return (window.frappe?.get_route?.() || []).join("/").toLowerCase();
	}

	function isActive(item) {
		const target = String(item.link_to || "").toLowerCase();
		const route = currentRoute();
		return Boolean(target) && (route === target || route.endsWith(`/${target}`));
	}

	function html(value) {
		return String(value || "").replace(/[&<>"']/g, (character) => ({
			"&": "&amp;",
			"<": "&lt;",
			">": "&gt;",
			'"': "&quot;",
			"'": "&#39;",
		})[character]);
	}

	function findNavbarTarget() {
		for (const selector of NAVBAR_TARGET_SELECTORS) {
			const candidates = Array.from(document.querySelectorAll(selector));
			const connected = candidates.find((node) => node.isConnected);
			if (connected) return { node: connected, selector };
		}
		return null;
	}

	function routeTo(item) {
		if (!window.frappe?.set_route) return;
		if (item.link_type === "Report") frappe.set_route("query-report", item.link_to);
		else if (item.link_type === "DocType") frappe.set_route("List", item.link_to);
		else frappe.set_route(item.link_to);
	}

	function renderFallback() {
		const panel = document.getElementById(FALLBACK_PANEL);
		if (!panel) return;
		const identity = profile();
		const initials = identity.name
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((part) => part[0])
			.join("")
			.toUpperCase() || "V";
		const sections = normalizeSections();
		const menuContent = sections.length
			? sections.map((section) => `<section class="vetedge-product-menu-section"><h3>${html(section.label)}</h3>${section.items.map((item) => `<button type="button" class="vetedge-product-menu-link ${isActive(item) ? "vetedge-product-menu-active" : ""}" data-link-type="${html(item.link_type)}" data-link-to="${html(item.link_to)}"><span class="vetedge-product-menu-link-icon">${html(item.icon)}</span><span>${html(item.label)}</span></button>`).join("")}</section>`).join("")
			: '<div class="vetedge-product-menu-empty">Veterinary navigation is loading…</div>';
		panel.innerHTML = `<div class="vetedge-product-menu-profile"><span class="vetedge-product-menu-avatar">${html(initials)}</span><div><strong>${html(identity.name)}</strong><small>${html(identity.email)}</small>${identity.company ? `<small>${html(identity.company)}${identity.branch ? ` · ${html(identity.branch)}` : ""}</small>` : ""}</div><span class="vetedge-product-menu-product">Veterinary</span></div><div class="vetedge-product-menu-scroll">${menuContent}</div>`;
	}

	function closeFallback() {
		const panel = document.getElementById(FALLBACK_PANEL);
		const trigger = document.getElementById(FALLBACK_TRIGGER);
		if (panel) panel.hidden = true;
		if (trigger) trigger.setAttribute("aria-expanded", "false");
	}

	function toggleFallback() {
		const panel = document.getElementById(FALLBACK_PANEL);
		const trigger = document.getElementById(FALLBACK_TRIGGER);
		if (!panel || !trigger) return;
		const open = panel.hidden;
		if (open) {
			renderFallback();
			panel.hidden = false;
		} else {
			panel.hidden = true;
		}
		trigger.setAttribute("aria-expanded", String(open));
	}

	function removeDuplicates(id, keep) {
		document.querySelectorAll(`#${id}`).forEach((node) => {
			if (node !== keep) node.remove();
		});
	}

	function mountFallback() {
		const existing = document.getElementById(FALLBACK_TRIGGER);
		if (existing?.isConnected) {
			removeDuplicates(FALLBACK_TRIGGER, existing);
			return { mounted: true, existing: true, reason: "already-mounted" };
		}
		existing?.remove();
		document.getElementById(FALLBACK_SLOT)?.remove();
		document.getElementById(FALLBACK_PANEL)?.remove();

		const target = findNavbarTarget();
		if (!target) return { mounted: false, reason: "navbar-not-ready" };

		const slot = document.createElement(target.node.tagName === "UL" ? "li" : "div");
		slot.id = FALLBACK_SLOT;
		slot.className = "vetedge-product-menu-slot";

		const trigger = document.createElement("button");
		trigger.id = FALLBACK_TRIGGER;
		trigger.type = "button";
		trigger.className = "vetedge-product-menu-trigger";
		trigger.setAttribute("aria-label", "Open product menu");
		trigger.setAttribute("aria-haspopup", "dialog");
		trigger.setAttribute("aria-expanded", "false");
		trigger.innerHTML = '<span aria-hidden="true">▦</span>';
		slot.appendChild(trigger);
		target.node.prepend(slot);

		const panel = document.createElement("aside");
		panel.id = FALLBACK_PANEL;
		panel.className = "vetedge-product-menu-panel";
		panel.hidden = true;
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-label", "VetEdge product menu");
		document.body.appendChild(panel);

		trigger.addEventListener("click", (event) => {
			event.stopPropagation();
			toggleFallback();
		});
		panel.addEventListener("click", (event) => {
			const link = event.target.closest(".vetedge-product-menu-link");
			if (!link) return;
			routeTo({ link_type: link.dataset.linkType, link_to: link.dataset.linkTo });
			closeFallback();
		});

		if (!fallbackEventsBound) {
			fallbackEventsBound = true;
			document.addEventListener("click", (event) => {
				const currentPanel = document.getElementById(FALLBACK_PANEL);
				const currentTrigger = document.getElementById(FALLBACK_TRIGGER);
				if (
					currentPanel &&
					currentTrigger &&
					!currentPanel.hidden &&
					!currentPanel.contains(event.target) &&
					!currentTrigger.contains(event.target)
				) closeFallback();
			});
			document.addEventListener("keydown", (event) => {
				if (event.key === "Escape") {
					closeFallback();
					window.EdgeSuiteUI?.closeProductMenu?.();
					window.EdgeUI?.closeProductMenu?.();
				}
			});
		}

		removeDuplicates(FALLBACK_TRIGGER, trigger);
		return { mounted: true, existing: false, reason: "mounted", selector: target.selector };
	}

	function registerEdgeUI() {
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		if (!runtime?.registerProductMenu) return { registered: false, reason: "runtime-adapter-unavailable" };
		runtime.registerProductMenu({
			product: PRODUCT,
			sections: normalizeSections(),
			profile: profile(),
			menu_source: "workspace_sidebar",
		});
		return { registered: true };
	}

	function mount() {
		const edge = registerEdgeUI();
		const fallback = mountFallback();
		if (!fallback.mounted) scheduleMount(fallback.reason, 150);
		return { mounted: fallback.mounted, edge, fallback };
	}

	function unmount() {
		closeFallback();
		document.getElementById(FALLBACK_SLOT)?.remove();
		document.getElementById(FALLBACK_TRIGGER)?.remove();
		document.getElementById(FALLBACK_PANEL)?.remove();
		return { unmounted: true };
	}

	function remount(reason = "manual") {
		unmount();
		const result = mount();
		return { ...result, reason };
	}

	function scheduleMount(reason = "lifecycle", delay = 0) {
		window.clearTimeout(scheduledMount);
		scheduledMount = window.setTimeout(() => {
			const trigger = document.getElementById(FALLBACK_TRIGGER);
			if (!trigger?.isConnected) mount();
			else renderFallback();
		}, delay);
		return { scheduled: true, reason };
	}

	function bindLifecycle() {
		if (lifecycleEventsBound) return;
		lifecycleEventsBound = true;
		LIFECYCLE_EVENTS.forEach((eventName) => {
			if (window.jQuery) {
				window.jQuery(document).on(`${eventName}.vetedge_product_menu`, () => scheduleMount(eventName));
			}
			window.frappe?.events?.on?.(eventName, () => scheduleMount(eventName));
		});
		window.frappe?.router?.on?.("change", () => scheduleMount("router-change"));

		if (window.MutationObserver && document.body) {
			observer = new MutationObserver(() => {
				const trigger = document.getElementById(FALLBACK_TRIGGER);
				if (!trigger?.isConnected) scheduleMount("navbar-mutation", 50);
			});
			observer.observe(document.body, { childList: true, subtree: true });
		}
	}

	function initialize() {
		bindLifecycle();
		mount();
	}

	window.VetedgeProductMenu = Object.assign(window.VetedgeProductMenu || {}, {
		mount,
		unmount,
		remount,
		close: closeFallback,
		selectors: NAVBAR_TARGET_SELECTORS.slice(),
	});

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", initialize, { once: true });
	} else {
		initialize();
	}
})();
