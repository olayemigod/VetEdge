// VetEdge Product Menu: canonical Workspace Sidebar rendered through EdgeUI or a safe Desk fallback.
(function () {
	if (typeof window === "undefined") return;
	const PRODUCT = "VetEdge";
	const EDGE_TRIGGER = "edge-product-menu-trigger";
	const FALLBACK_TRIGGER = "vetedge-product-menu-trigger";
	const FALLBACK_PANEL = "vetedge-product-menu-panel";
	let fallbackEventsBound = false;

	function canonicalSidebar() {
		const sidebars = window.frappe && frappe.boot && frappe.boot.workspace_sidebar_item;
		return sidebars && (sidebars.vetedge || sidebars.veterinary);
	}
	function normalizeItem(item) {
		return { label: item.label, icon: item.icon || "list", link_type: item.link_type, link_to: item.link_to,
			route: item.route || "", display_depends_on: item.display_depends_on || "", roles: item.roles || [],
			feature_key: item.feature_key || "", visible: item.hidden !== 1 };
	}
	function normalizeSections() {
		const sections = []; let section;
		((canonicalSidebar() || {}).items || []).forEach((item) => {
			if (item.type === "Section Break") { section = { label: item.label, icon: item.icon || "", collapsible: !!item.collapsible, keep_closed: !!item.keep_closed, items: [] }; sections.push(section); }
			else if (item.type === "Link" && section) section.items.push(normalizeItem(item));
		});
		return sections.filter((item) => item.items.length);
	}
	function profile() {
		const boot = (window.frappe && frappe.boot) || {};
		const user = (window.frappe && frappe.session && frappe.session.user) || (boot.user && boot.user.name) || "";
		return { name: (boot.user && (boot.user.full_name || boot.user.name)) || user || "Veterinary User", email: user,
			company: (boot.sysdefaults && boot.sysdefaults.company) || "", branch: (boot.edgesuite_product_menu && boot.edgesuite_product_menu.branch) || "" };
	}
	function currentRoute() { return ((window.frappe && frappe.get_route && frappe.get_route()) || []).join("/").toLowerCase(); }
	function isActive(item) { const target = String(item.link_to || "").toLowerCase(); const route = currentRoute(); return !!target && (route === target || route.endsWith(`/${target}`)); }
	function html(value) { return String(value || "").replace(/[&<>"']/g, (char) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[char]); }
	function visibleNavbar() {
		const selectors = [".navbar .navbar-nav.ms-auto", ".navbar .navbar-nav.ml-auto", ".navbar .navbar-right", ".navbar .navbar-nav", "header.navbar", ".navbar", ".desktop-navbar"];
		for (const selector of selectors) for (const node of document.querySelectorAll(selector)) {
			const box = node.getBoundingClientRect(); if (node.isConnected && box.width > 0 && box.height > 0 && getComputedStyle(node).visibility !== "hidden") return node;
		}
		return null;
	}
	function routeTo(item) {
		if (!window.frappe || !frappe.set_route) return;
		if (item.link_type === "Report") frappe.set_route("query-report", item.link_to);
		else if (item.link_type === "DocType") frappe.set_route("List", item.link_to);
		else frappe.set_route(item.link_to);
	}
	function renderFallback() {
		const panel = document.getElementById(FALLBACK_PANEL); if (!panel) return;
		const identity = profile(); const initials = identity.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "V";
		panel.innerHTML = `<div class="vetedge-product-menu-profile"><span class="vetedge-product-menu-avatar">${html(initials)}</span><div><strong>${html(identity.name)}</strong><small>${html(identity.email)}</small>${identity.company ? `<small>${html(identity.company)}${identity.branch ? ` · ${html(identity.branch)}` : ""}</small>` : ""}</div><span class="vetedge-product-menu-product">Veterinary</span></div><div class="vetedge-product-menu-scroll">${normalizeSections().map((section) => `<section class="vetedge-product-menu-section"><h3>${html(section.label)}</h3>${section.items.map((item) => `<button type="button" class="vetedge-product-menu-link ${isActive(item) ? "vetedge-product-menu-active" : ""}" data-link-type="${html(item.link_type)}" data-link-to="${html(item.link_to)}"><span class="vetedge-product-menu-link-icon">${html(item.icon)}</span><span>${html(item.label)}</span></button>`).join("")}</section>`).join("")}</div>`;
	}
	function closeFallback() { const panel = document.getElementById(FALLBACK_PANEL); const trigger = document.getElementById(FALLBACK_TRIGGER); if (panel) panel.hidden = true; if (trigger) trigger.setAttribute("aria-expanded", "false"); }
	function toggleFallback() { const panel = document.getElementById(FALLBACK_PANEL); if (!panel) return; const open = panel.hidden; if (open) { renderFallback(); panel.hidden = false; } else panel.hidden = true; document.getElementById(FALLBACK_TRIGGER).setAttribute("aria-expanded", String(open)); }
	function mountFallback() {
		if (document.getElementById(EDGE_TRIGGER) || document.getElementById(FALLBACK_TRIGGER) || !normalizeSections().length) return false;
		const navbar = visibleNavbar(); if (!navbar) return false;
		const trigger = document.createElement("button"); trigger.id = FALLBACK_TRIGGER; trigger.type = "button"; trigger.className = "vetedge-product-menu-trigger";
		trigger.setAttribute("aria-label", "Open product menu"); trigger.setAttribute("aria-haspopup", "dialog"); trigger.setAttribute("aria-expanded", "false"); trigger.innerHTML = '<span aria-hidden="true">▦</span>';
		navbar.appendChild(trigger);
		const panel = document.createElement("aside"); panel.id = FALLBACK_PANEL; panel.className = "vetedge-product-menu-panel"; panel.hidden = true; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "VetEdge product menu"); document.body.appendChild(panel);
		trigger.addEventListener("click", (event) => { event.stopPropagation(); toggleFallback(); });
		panel.addEventListener("click", (event) => { const link = event.target.closest(".vetedge-product-menu-link"); if (!link) return; routeTo({ link_type: link.dataset.linkType, link_to: link.dataset.linkTo }); closeFallback(); });
		if (!fallbackEventsBound) { fallbackEventsBound = true; document.addEventListener("click", (event) => { const p = document.getElementById(FALLBACK_PANEL), t = document.getElementById(FALLBACK_TRIGGER); if (p && !p.hidden && !p.contains(event.target) && !t.contains(event.target)) closeFallback(); }); document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeFallback(); window.EdgeUI && window.EdgeUI.closeProductMenu && window.EdgeUI.closeProductMenu(); } }); }
		return true;
	}
	function registerEdgeUI() { if (window.EdgeUI && window.EdgeUI.registerProductMenu && normalizeSections().length) window.EdgeUI.registerProductMenu({ product: PRODUCT, sections: normalizeSections(), profile: profile(), menu_source: "workspace_sidebar" }); }
	function mount(attempt) {
		registerEdgeUI();
		if (mountFallback()) return;
		if (document.getElementById(EDGE_TRIGGER)) return;
		if (attempt < 12) window.setTimeout(() => mount(attempt + 1), 100);
	}
	function initialize() { mount(0); if (window.frappe && frappe.router && frappe.router.on) frappe.router.on("change", () => window.requestAnimationFrame(() => mount(0))); }
	window.VetedgeProductMenu = Object.assign(window.VetedgeProductMenu || {}, { mount: () => mount(0), close: closeFallback });
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true }); else initialize();
})();