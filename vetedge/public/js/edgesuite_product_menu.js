// VetEdge Product Menu: canonical Workspace Sidebar consumed by standalone EdgeSuite UI.
(function () {
	if (typeof window === "undefined") return;
	const PRODUCT = "VetEdge";
	const EDGE_TRIGGER = "edge-product-menu-trigger";
	const FALLBACK_HOST = "vetedge-product-menu-host";
	const FALLBACK_TRIGGER = "vetedge-product-menu-trigger";
	const FALLBACK_PANEL = "vetedge-product-menu-panel";
	const MAX_RUNTIME_ATTEMPTS = 40;
	let fallbackEventsBound = false;
	let mountTimer;

	function canonicalSidebar() {
		const sidebars = window.frappe && frappe.boot && frappe.boot.workspace_sidebar_item;
		return sidebars && (sidebars.vetedge || sidebars.veterinary);
	}
	function normalizeItem(item) {
		return { label: item.label, icon: item.icon || "list", link_type: item.link_type, link_to: item.link_to,
			route: item.route || "", roles: item.roles || [], feature_key: item.feature_key || "", visible: item.hidden !== 1 };
	}
	function normalizeSections() {
		const sections = []; let section;
		((canonicalSidebar() || {}).items || []).forEach((item) => {
			if (item.type === "Section Break") { section = { label: item.label, icon: item.icon || "", items: [] }; sections.push(section); }
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
	function edgeRuntime() { return window.EdgeSuiteUI || window.EdgeUI || null; }
	function currentRoute() { return ((window.frappe && frappe.get_route && frappe.get_route()) || []).join("/").toLowerCase(); }
	function isActive(item) { const target = String(item.link_to || "").toLowerCase(), route = currentRoute(); return !!target && (route === target || route.endsWith(`/${target}`) || route.includes(`/${target}/`)); }
	function html(value) { return String(value || "").replace(/[&<>"']/g, (character) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" })[character]); }
	function itemIcon(name) {
		try { const icon = window.frappe && frappe.utils && frappe.utils.icon && frappe.utils.icon(name || "list", "sm"); if (icon) return icon; } catch (error) { /* fallback below */ }
		return '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="5" width="16" height="3" rx="1.5"></rect><rect x="4" y="10.5" width="16" height="3" rx="1.5"></rect><rect x="4" y="16" width="16" height="3" rx="1.5"></rect></svg>';
	}
	function waffleIcon() {
		return '<svg class="vetedge-product-menu-waffle" viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="5" r="1.65"></circle><circle cx="12" cy="5" r="1.65"></circle><circle cx="19" cy="5" r="1.65"></circle><circle cx="5" cy="12" r="1.65"></circle><circle cx="12" cy="12" r="1.65"></circle><circle cx="19" cy="12" r="1.65"></circle><circle cx="5" cy="19" r="1.65"></circle><circle cx="12" cy="19" r="1.65"></circle><circle cx="19" cy="19" r="1.65"></circle></svg>';
	}
	function visibleNavbar() {
		const selectors = [".navbar .navbar-nav.ms-auto", ".navbar .navbar-nav.ml-auto", ".navbar .navbar-right", ".navbar .navbar-nav:last-of-type", "header.navbar .navbar-nav", ".desktop-navbar .navbar-nav", "header.navbar", ".navbar", ".desktop-navbar"];
		for (const selector of selectors) for (const node of Array.from(document.querySelectorAll(selector)).reverse()) {
			const box = node.getBoundingClientRect(), style = getComputedStyle(node);
			if (node.isConnected && box.width > 0 && box.height > 0 && style.visibility !== "hidden" && style.display !== "none") return node;
		}
		return null;
	}
	function routeTo(item) {
		if (!window.frappe || !frappe.set_route) return;
		if (item.route) frappe.set_route(...item.route.replace(/^\/+/, "").split("/").filter(Boolean));
		else if (item.link_type === "Report") frappe.set_route("query-report", item.link_to);
		else if (item.link_type === "DocType") frappe.set_route("List", item.link_to);
		else frappe.set_route(item.link_to);
	}
	function renderFallback() {
		const panel = document.getElementById(FALLBACK_PANEL); if (!panel) return;
		const identity = profile(), initials = identity.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || "V";
		panel.innerHTML = `<div class="vetedge-product-menu-profile"><span class="vetedge-product-menu-avatar">${html(initials)}</span><div><strong>${html(identity.name)}</strong><small>${html(identity.email)}</small>${identity.company ? `<small>${html(identity.company)}${identity.branch ? ` · ${html(identity.branch)}` : ""}</small>` : ""}</div><span class="vetedge-product-menu-product">Veterinary</span></div><div class="vetedge-product-menu-scroll">${normalizeSections().map((section) => `<section class="vetedge-product-menu-section"><h3>${html(section.label)}</h3><div class="vetedge-product-menu-items">${section.items.map((item) => `<button type="button" class="vetedge-product-menu-link ${isActive(item) ? "vetedge-product-menu-active" : ""}" data-link-type="${html(item.link_type)}" data-link-to="${html(item.link_to)}" data-route="${html(item.route)}"><span class="vetedge-product-menu-link-icon" aria-hidden="true">${itemIcon(item.icon)}</span><span>${html(item.label)}</span></button>`).join("")}</div></section>`).join("")}</div>`;
	}
	function closeFallback() { const panel = document.getElementById(FALLBACK_PANEL), trigger = document.getElementById(FALLBACK_TRIGGER); if (panel) panel.hidden = true; if (trigger) trigger.setAttribute("aria-expanded", "false"); }
	function toggleFallback() { const panel = document.getElementById(FALLBACK_PANEL), trigger = document.getElementById(FALLBACK_TRIGGER); if (!panel || !trigger) return; const open = panel.hidden; if (open) renderFallback(); panel.hidden = !open; trigger.setAttribute("aria-expanded", String(open)); }
	function removeFallback() { document.getElementById(FALLBACK_HOST)?.remove(); document.getElementById(FALLBACK_PANEL)?.remove(); }
	function mountFallback() {
		if (document.getElementById(EDGE_TRIGGER) || document.getElementById(FALLBACK_TRIGGER) || !normalizeSections().length) return false;
		const navbar = visibleNavbar(); if (!navbar) return false;
		const host = document.createElement(navbar.matches("ul, ol") ? "li" : "span"); host.id = FALLBACK_HOST; host.className = "vetedge-product-menu-host";
		const trigger = document.createElement("button"); trigger.id = FALLBACK_TRIGGER; trigger.type = "button"; trigger.className = "vetedge-product-menu-trigger";
		trigger.setAttribute("aria-label", "Open product menu"); trigger.setAttribute("aria-haspopup", "dialog"); trigger.setAttribute("aria-expanded", "false"); trigger.innerHTML = waffleIcon(); host.appendChild(trigger); navbar.appendChild(host);
		const panel = document.createElement("aside"); panel.id = FALLBACK_PANEL; panel.className = "vetedge-product-menu-panel"; panel.hidden = true; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "VetEdge product menu"); document.body.appendChild(panel);
		trigger.addEventListener("click", (event) => { event.stopPropagation(); toggleFallback(); });
		panel.addEventListener("click", (event) => { const link = event.target.closest(".vetedge-product-menu-link"); if (!link) return; routeTo({ link_type: link.dataset.linkType, link_to: link.dataset.linkTo, route: link.dataset.route }); closeFallback(); });
		if (!fallbackEventsBound) { fallbackEventsBound = true; document.addEventListener("click", (event) => { const p = document.getElementById(FALLBACK_PANEL), t = document.getElementById(FALLBACK_TRIGGER); if (p && !p.hidden && !p.contains(event.target) && !t?.contains(event.target)) closeFallback(); }); document.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeFallback(); edgeRuntime()?.closeProductMenu?.(); } }); }
		return true;
	}
	function registerSharedMenu() {
		const edgeUI = edgeRuntime(), sections = normalizeSections();
		if (!edgeUI || typeof edgeUI.registerProductMenu !== "function" || !sections.length) return false;
		removeFallback(); edgeUI.registerProductMenu({ product: PRODUCT, sections, profile: profile(), menu_source: "workspace_sidebar" }); edgeUI.refreshProductMenu?.(); return true;
	}
	function mount(attempt) { window.clearTimeout(mountTimer); if (registerSharedMenu()) return; if (attempt < MAX_RUNTIME_ATTEMPTS) { mountTimer = window.setTimeout(() => mount(attempt + 1), 100); return; } mountFallback(); }
	function remount() { window.requestAnimationFrame(() => mount(0)); }
	function initialize() { mount(0); if (window.frappe && frappe.router && frappe.router.on) frappe.router.on("change", remount); ["desktop_screen", "sidebar_setup", "toolbar_setup", "page-change"].forEach((eventName) => document.addEventListener(eventName, remount)); }
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true }); else initialize();
})();
