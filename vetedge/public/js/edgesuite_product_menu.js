// VetEdge Product Menu: cross-product navigation for the Frappe v16 Desk navbar.
(function () {
	"use strict";

	if (typeof window === "undefined") return;

	const PRODUCT = "VetEdge";
	const FALLBACK_SLOT = "vetedge-product-menu-slot";
	const FALLBACK_TRIGGER = "vetedge-product-menu-trigger";
	const FALLBACK_PANEL = "vetedge-product-menu-panel";
	const PAGE_CONTEXT_SELECTOR = '[data-edge-product="vetedge"] .edge-topbar-context';
	// Kept as an array for the public menu API. The current target remains page-local
	// so VetEdge does not inject into unstable Frappe navbar DOM.
	const NAVBAR_TARGET_SELECTORS = [PAGE_CONTEXT_SELECTOR];
	const LIFECYCLE_EVENTS = ["toolbar_setup", "page-change", "desktop_screen", "sidebar_setup"];
	const FALLBACK_ROUTES = [
		{ label: "Executive Dashboard", icon: "dashboard", link_type: "Page", link_to: "vetedge-executive-dashboard" },
		{ label: "Stock Expiry Monitor", icon: "stock", link_type: "Page", link_to: "stock-expiry-monitor" },
		{ label: "Veterinary Settings", icon: "settings", link_type: "DocType", link_to: "Veterinary Settings" },
	];
	// Frappe installations may not populate route configuration in boot. Keep this
	// local alias defined in every case; never read an undeclared global identifier.
	const configured_routes = Array.isArray(window.configured_routes)
		? window.configured_routes
		: [];
	const state = {
		loaded: true,
		lifecycleSubscriptions: [],
		observerActive: false,
		lastMountResult: null,
		lastTarget: null,
		lastError: null,
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
		const fallbackRoutes = configured_routes.length ? configured_routes : FALLBACK_ROUTES;
		return populated.length
			? populated
			: [{ label: "Veterinary", icon: "apps", items: fallbackRoutes.map(normalizeItem) }];
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

	const MENU_ICON_GLYPHS = {
		dashboard: "▦",
		stock: "◫",
		settings: "⚙",
		report: "▤",
		"file-text": "▤",
		bell: "●",
		list: "≡",
		home: "⌂",
		user: "●",
	};

	function menuIcon(icon) {
		const name = String(icon || "list").replace(/^icon-/, "").toLowerCase();
		const glyph = MENU_ICON_GLYPHS[name] || MENU_ICON_GLYPHS.list;
		return `<span class="vetedge-product-menu-icon-glyph" aria-hidden="true">${glyph}</span>`;
	}

	function inspectTargets() {
		const nodes = Array.from(document.querySelectorAll(NAVBAR_TARGET_SELECTORS.join(", ")));
		return [{
			selector: PAGE_CONTEXT_SELECTOR,
			count: nodes.length,
			connected: nodes.filter((node) => node.isConnected).length,
			visible: nodes.filter((node) => {
				if (!node.isConnected) return false;
				const style = window.getComputedStyle?.(node);
				return style?.display !== "none" && style?.visibility !== "hidden";
			}).length,
		}];
	}

	function findPageContextTarget() {
		const node = Array.from(document.querySelectorAll(NAVBAR_TARGET_SELECTORS.join(", "))).find((candidate) => {
			if (!candidate.isConnected) return false;
			const style = window.getComputedStyle?.(candidate);
			return style?.display !== "none" && style?.visibility !== "hidden";
		});
		if (!node) {
			state.lastTarget = { selector: PAGE_CONTEXT_SELECTOR, visible: false };
			return null;
		}
		state.lastTarget = { selector: PAGE_CONTEXT_SELECTOR, visible: true };
		return { node, selector: PAGE_CONTEXT_SELECTOR, visible: true };
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
		const quickAccess = (configured_routes.length ? configured_routes : FALLBACK_ROUTES).slice(0, 2);
		const menuLink = (item, variant = "") => `<button type="button" class="vetedge-product-menu-link ${variant} ${isActive(item) ? "vetedge-product-menu-active" : ""}" data-link-type="${html(item.link_type)}" data-link-to="${html(item.link_to)}"><span class="vetedge-product-menu-link-icon" aria-hidden="true">${menuIcon(item.icon)}</span><span class="vetedge-product-menu-link-copy"><strong>${html(item.label)}</strong><small>${html(item.link_type || "Workspace")}</small></span></button>`;
		panel.innerHTML = `
			<div class="vetedge-product-menu-profile">
				<span class="vetedge-product-menu-avatar">${html(initials)}</span>
				<div>
					<strong>${html(identity.name)}</strong>
					<small>${html(identity.company || "Veterinary")} · ${html(identity.branch)}</small>
				</div>
				<span class="vetedge-product-menu-product">Veterinary</span>
			</div>
			<div class="vetedge-product-menu-scroll">
				<section class="vetedge-product-menu-quick-access" aria-label="Quick access">
					<div class="vetedge-product-menu-section-heading"><h3>Quick access</h3><span>VetEdge workspace</span></div>
					<div class="vetedge-product-menu-quick-grid">${quickAccess.map((item) => menuLink(item, "vetedge-product-menu-quick-link")).join("")}</div>
				</section>
				<div class="vetedge-product-menu-grid">${sections.map((section) => `<section class="vetedge-product-menu-section"><h3>${html(section.label)}</h3><div class="vetedge-product-menu-section-links">${section.items.map((item) => menuLink(item)).join("")}</div></section>`).join("")}</div>
			</div>`;
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
			return result(true, "already-mounted", state.lastTarget?.selector || PAGE_CONTEXT_SELECTOR);
		}
		existing?.remove();
		document.getElementById(FALLBACK_SLOT)?.remove();
		document.getElementById(FALLBACK_PANEL)?.remove();

		const target = findPageContextTarget();
		if (!target) return result(false, "no-page-context", null);

		const slot = document.createElement(target.node.tagName === "UL" ? "li" : "div");
		slot.id = FALLBACK_SLOT;
		slot.className = "vetedge-product-menu-slot vetedge-product-menu-slot--context";
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
		// The standalone runtime may expose a generic menu adapter. VetEdge owns this
		// launcher so the adapter cannot replace the branded, grouped local panel.
		runtime?.closeProductMenu?.();
		return {
			registered: false,
			reason: "vetedge-owned-mega-menu",
			standaloneRuntime: Boolean(runtime),
		};
	}

	function mount() {
		debug("mount-invoked");
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
		if (!mounted.mounted && mounted.reason !== "no-page-context") scheduleMount(mounted.reason, 250);
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
				if (!trigger?.isConnected && findPageContextTarget()) {
					scheduleMount("page-context-mutation", 75);
				}
			});
			observer.observe(document.body, { childList: true, subtree: true });
			state.observerActive = true;
		}
	}

	function diagnose() {
		return {
			loaded: state.loaded,
			currentMenuNodeCount: document.querySelectorAll(`#${FALLBACK_TRIGGER}`).length,
			selectedNavbarTarget: state.lastTarget,
			targets: inspectTargets(),
			lifecycleSubscriptions: state.lifecycleSubscriptions.slice(),
			observerActive: state.observerActive,
			lastMountResult: state.lastMountResult,
			lastError: state.lastError,
		};
	}

	function initialize() {
		bindLifecycle();
	}

	window.VetedgeProductMenu = Object.assign(window.VetedgeProductMenu || {}, {
		mount,
		unmount,
		remount,
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
