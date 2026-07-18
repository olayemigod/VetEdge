// VetEdge Product Menu: cross-product navigation for the Frappe v16 Desk navbar.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const PRODUCT = "VetEdge";
	const FALLBACK_SLOT = "vetedge-product-menu-slot";
	const FALLBACK_TRIGGER = "vetedge-product-menu-trigger";
	const FALLBACK_PANEL = "vetedge-product-menu-panel";
	const NAVBAR_TARGET_SELECTORS = [
		".page-head .page-actions",
		".page-head-content .page-actions",
		".page-actions",
		"header .navbar .navbar-right",
		".navbar .navbar-right",
		"header .navbar .navbar-nav.ms-auto",
		"header .navbar .navbar-nav.ml-auto",
		"header .navbar .navbar-collapse .navbar-nav",
		"header .navbar .navbar-collapse",
		"header .navbar .container",
	];
	const LIFECYCLE_EVENTS = ["toolbar_setup", "page-change", "desktop_screen", "sidebar_setup"];
	const FALLBACK_ROUTES = [
		{ label: "Executive Dashboard", icon: "dashboard", link_type: "Page", link_to: "vetedge-executive-dashboard" },
		{ label: "Stock Expiry Monitor", icon: "stock", link_type: "Page", link_to: "stock-expiry-monitor" },
		{ label: "Veterinary Settings", icon: "settings", link_type: "DocType", link_to: "Veterinary Settings" },
	];
	const state = {
		loaded: true,
		lifecycleSubscriptions: [],
		observerActive: false,
		lastMountResult: null,
		lastTarget: null,
		lastError: null,
		inlineMode: false,
	};
	let fallbackEventsBound = false;
	let lifecycleEventsBound = false;
	let observer;
	let scheduledMount;

	function debugEnabled() {
		return Boolean(
			window.frappe?.boot?.developer_mode ||
			window.localStorage?.getItem("vetedge_product_menu_debug") === "1"
		);
	}

	function debug(event, detail) {
		if (debugEnabled()) console.debug("[VetedgeProductMenu]", event, detail || "");
	}

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
			visible: item.hidden !== 1,
		};
	}

	function normalizeSections() {
		const sections = [];
		let section;
		((canonicalSidebar() || {}).items || []).forEach((item) => {
			if (item.type === "Section Break") {
				section = { label: item.label, icon: item.icon || "", items: [] };
				sections.push(section);
			} else if (item.type === "Link" && section && item.hidden !== 1) {
				section.items.push(normalizeItem(item));
			}
		});
		const populated = sections.filter((item) => item.items.length);
		return populated.length
			? populated
			: [{ label: "Veterinary", icon: "apps", items: FALLBACK_ROUTES.map(normalizeItem) }];
	}

	function profile() {
		const boot = window.frappe?.boot || {};
		const user = window.frappe?.session?.user || boot.user?.name || "";
		return {
			name: boot.user?.full_name || boot.user?.name || user || "Veterinary User",
			email: user,
			company: boot.sysdefaults?.company || "",
			branch: boot.edgesuite_product_menu?.branch || "All Branches",
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
			"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
		})[character]);
	}

	function inspectTargets() {
		return NAVBAR_TARGET_SELECTORS.map((selector) => {
			const nodes = Array.from(document.querySelectorAll(selector));
			return {
				selector,
				count: nodes.length,
				connected: nodes.filter((node) => node.isConnected).length,
				visible: nodes.filter((node) => {
					if (!node.isConnected) return false;
					const style = window.getComputedStyle?.(node);
					return style?.display !== "none" && style?.visibility !== "hidden";
				}).length,
			};
		});
	}

	function findNavbarTarget() {
		const inspected = inspectTargets();
		for (const requireVisible of [true, false]) {
			for (const target of inspected) {
				if (!target.connected || (requireVisible && !target.visible)) continue;
				const node = Array.from(document.querySelectorAll(target.selector)).find((candidate) => {
					if (!candidate.isConnected) return false;
					if (!requireVisible) return true;
					const style = window.getComputedStyle?.(candidate);
					return style?.display !== "none" && style?.visibility !== "hidden";
				});
				if (node) {
					state.lastTarget = { selector: target.selector, visible: target.visible > 0 };
					return { node, selector: target.selector, visible: target.visible > 0 };
				}
			}
		}
		state.lastTarget = { selector: "body", visible: true, floating: true };
		return { node: document.body, selector: "body", visible: true, floating: true };
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
		const initials = identity.name.split(/\s+/).filter(Boolean).slice(0, 2)
			.map((part) => part[0]).join("").toUpperCase() || "V";
		const sections = normalizeSections();
		panel.innerHTML = `<div class="vetedge-product-menu-profile"><span class="vetedge-product-menu-avatar">${html(initials)}</span><div><strong>${html(identity.name)}</strong><small>${html(identity.email)}</small><small>${html(identity.company)} · ${html(identity.branch)}</small></div><span class="vetedge-product-menu-product">Veterinary</span></div><div class="vetedge-product-menu-scroll">${sections.map((section) => `<section class="vetedge-product-menu-section"><h3>${html(section.label)}</h3>${section.items.map((item) => `<button type="button" class="vetedge-product-menu-link ${isActive(item) ? "vetedge-product-menu-active" : ""}" data-link-type="${html(item.link_type)}" data-link-to="${html(item.link_to)}"><span class="vetedge-product-menu-link-icon">${html(item.icon)}</span><span>${html(item.label)}</span></button>`).join("")}</section>`).join("")}</div>`;
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
		if (open) renderFallback();
		panel.hidden = !open;
		trigger.setAttribute("aria-expanded", String(open));
	}

	function removeDuplicates(id, keep) {
		document.querySelectorAll(`#${id}`).forEach((node) => {
			if (node !== keep) node.remove();
		});
	}

	function result(mounted, reason, selector, extra = {}) {
		const value = { mounted, selector: selector || null, reason, ...extra };
		state.lastMountResult = value;
		debug("mount-result", value);
		return value;
	}

	function mountFallback() {
		const existing = document.getElementById(FALLBACK_TRIGGER);
		if (existing?.isConnected) {
			removeDuplicates(FALLBACK_TRIGGER, existing);
			return result(true, "already-mounted", existing.closest(`#${FALLBACK_SLOT}`)?.parentElement?.matches(".navbar-right") ? ".navbar-right" : state.lastTarget?.selector);
		}
		existing?.remove();
		document.getElementById(FALLBACK_SLOT)?.remove();
		document.getElementById(FALLBACK_PANEL)?.remove();

		const target = findNavbarTarget();
		debug("targets-checked", inspectTargets());
		if (!target) return result(false, "no-navbar-target", null);

		const slot = document.createElement(target.node.tagName === "UL" ? "li" : "div");
		slot.id = FALLBACK_SLOT;
		slot.className = target.floating
			? "vetedge-product-menu-slot vetedge-product-menu-slot--floating"
			: "vetedge-product-menu-slot";
		const trigger = document.createElement("button");
		trigger.id = FALLBACK_TRIGGER;
		trigger.type = "button";
		trigger.className = "btn btn-default icon-btn vetedge-product-menu-trigger";
		trigger.setAttribute("aria-label", "Open product menu");
		trigger.setAttribute("aria-haspopup", "dialog");
		trigger.setAttribute("aria-expanded", "false");
		trigger.innerHTML = '<svg class="vetedge-product-menu-waffle-icon" viewBox="0 0 20 20" aria-hidden="true" focusable="false"><circle cx="4" cy="4" r="1.6"></circle><circle cx="10" cy="4" r="1.6"></circle><circle cx="16" cy="4" r="1.6"></circle><circle cx="4" cy="10" r="1.6"></circle><circle cx="10" cy="10" r="1.6"></circle><circle cx="16" cy="10" r="1.6"></circle><circle cx="4" cy="16" r="1.6"></circle><circle cx="10" cy="16" r="1.6"></circle><circle cx="16" cy="16" r="1.6"></circle></svg>';
		slot.appendChild(trigger);
		target.node.prepend(slot);

		const panel = document.createElement("aside");
		panel.id = FALLBACK_PANEL;
		panel.className = "vetedge-product-menu-panel";
		panel.hidden = true;
		panel.setAttribute("role", "dialog");
		panel.setAttribute("aria-label", "VetEdge product menu");
		document.body.appendChild(panel);
		trigger.addEventListener("click", (event) => { event.stopPropagation(); toggleFallback(); });
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
				if (currentPanel && currentTrigger && !currentPanel.hidden &&
					!currentPanel.contains(event.target) && !currentTrigger.contains(event.target)) closeFallback();
			});
			document.addEventListener("keydown", (event) => {
				if (event.key === "Escape") {
					closeFallback();
					(window.EdgeSuiteUI || window.EdgeUI)?.closeProductMenu?.();
				}
			});
		}
		removeDuplicates(FALLBACK_TRIGGER, trigger);
		debug("node-inserted", { selector: target.selector, visible: target.visible });
		return result(true, "inserted", target.selector, { targetVisible: target.visible });
	}

	function registerEdgeUI() {
		const runtime = window.EdgeSuiteUI || window.EdgeUI;
		if (!runtime?.registerProductMenu) return { registered: false, reason: "adapter-unavailable" };
		try {
			runtime.registerProductMenu({
				product: PRODUCT,
				sections: normalizeSections(),
				profile: profile(),
				menu_source: canonicalSidebar() ? "workspace_sidebar" : "configured_routes",
			});
			return { registered: true };
		} catch (error) {
			state.lastError = { stage: "runtime-adapter", message: error?.message || String(error) };
			debug("runtime-adapter-failed", state.lastError);
			return { registered: false, reason: "adapter-failed", error: state.lastError.message };
		}
	}

	function mount() {
		debug("mount-invoked");
		if (state.inlineMode) return result(false, "inline-shell-managed", "vetedge-suite-context-bar");
		state.lastError = null;
		let mounted;
		try {
			mounted = mountFallback();
		} catch (error) {
			state.lastError = { stage: "dom-fallback", message: error?.message || String(error) };
			debug("dom-fallback-failed", state.lastError);
			mounted = result(false, "dom-fallback-failed", null, { error: state.lastError.message });
		}
		const edge = registerEdgeUI();
		if (!mounted.mounted) scheduleMount(mounted.reason, 250);
		return { ...mounted, edge };
	}

	function unmount() {
		closeFallback();
		document.getElementById(FALLBACK_SLOT)?.remove();
		document.getElementById(FALLBACK_TRIGGER)?.remove();
		document.getElementById(FALLBACK_PANEL)?.remove();
		return { unmounted: true };
	}

	function remount(reason = "manual") {
		debug("remount-invoked", reason);
		unmount();
		const mounted = mount();
		return { ...mounted, remountReason: reason };
	}

	function scheduleMount(reason = "lifecycle", delay = 0) {
		if (state.inlineMode) return { scheduled: false, reason: "inline-shell-managed" };
		window.clearTimeout(scheduledMount);
		scheduledMount = window.setTimeout(() => {
			const trigger = document.getElementById(FALLBACK_TRIGGER);
			if (!trigger?.isConnected) {
				debug("node-removed", reason);
				mount();
			} else {
				renderFallback();
			}
		}, delay);
		return { scheduled: true, reason };
	}

	function bindLifecycle() {
		if (lifecycleEventsBound) return;
		lifecycleEventsBound = true;
		LIFECYCLE_EVENTS.forEach((eventName) => {
			if (window.jQuery) {
				window.jQuery(document).on(`${eventName}.vetedge_product_menu`, () => scheduleMount(eventName));
				state.lifecycleSubscriptions.push(`document:${eventName}`);
			}
			if (window.frappe?.events?.on) {
				frappe.events.on(eventName, () => scheduleMount(eventName));
				state.lifecycleSubscriptions.push(`frappe:${eventName}`);
			}
		});
		if (window.frappe?.router?.on) {
			frappe.router.on("change", () => scheduleMount("router-change"));
			state.lifecycleSubscriptions.push("router:change");
		}
		if (window.MutationObserver && document.body) {
			observer = new MutationObserver(() => {
				const trigger = document.getElementById(FALLBACK_TRIGGER);
				const floating = document.getElementById(FALLBACK_SLOT)?.classList.contains("vetedge-product-menu-slot--floating");
				const visibleNavbarReady = inspectTargets().some((target) => target.visible > 0);
				if (!trigger?.isConnected) scheduleMount("navbar-mutation", 75);
				else if (floating && visibleNavbarReady) remount("navbar-became-visible");
			});
			observer.observe(document.body, { childList: true, subtree: true });
			state.observerActive = true;
		}
	}

	function setInlineMode(enabled) {
		state.inlineMode = Boolean(enabled);
		if (state.inlineMode) return unmount();
		return mount();
	}

	function getSections() {
		return normalizeSections();
	}

	function navigate(item) {
		routeTo(item);
		return { navigated: Boolean(item?.link_to), item };
	}

	function diagnose() {
		return {
			loaded: state.loaded,
			currentMenuNodeCount: document.querySelectorAll(`#${FALLBACK_TRIGGER}`).length,
			selectedNavbarTarget: state.lastTarget,
			targets: inspectTargets(),
			lifecycleSubscriptions: state.lifecycleSubscriptions.slice(),
			observerActive: state.observerActive,
			inlineMode: state.inlineMode,
			lastMountResult: state.lastMountResult,
			lastError: state.lastError,
		};
	}

	function initialize() {
		bindLifecycle();
		mount();
	}

	window.VetedgeProductMenu = Object.assign(window.VetedgeProductMenu || {}, {
		mount,
		unmount,
		remount,
		setInlineMode,
		getSections,
		navigate,
		close: closeFallback,
		diagnose,
		selectors: NAVBAR_TARGET_SELECTORS.slice(),
	});

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", initialize, { once: true });
	} else {
		initialize();
	}
})();
